#!/usr/bin/env python3
"""Copy allowlisted execution evidence without following links or overwriting."""

from __future__ import annotations

import argparse
import errno
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import secrets


EVIDENCE_NAME = re.compile(
    r"^(?:(?:generalized_constraints|generalized_latency)_[0-9a-f]{32}\."
    r"(?:json|md)|run_[0-9]+\.json)$"
)
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)


class EvidenceMigrationError(OSError):
    def __init__(self, message: str, imported: list[str]):
        super().__init__(message)
        self.imported = tuple(imported)


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _open_directory(path: Path) -> int:
    path = _absolute_path(path)
    descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise ValueError(f"Invalid evidence path component: {component!r}")
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise ValueError(
                        f"Symlink is not allowed; invalid directory component in "
                        f"evidence path: "
                        f"{path}"
                    ) from exc
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _secure_destination(
    parent_descriptor: int,
    destination_name: str,
    gid: int,
) -> tuple[int, bool]:
    def open_destination() -> int:
        try:
            return os.open(
                destination_name,
                _DIRECTORY_FLAGS,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise ValueError(
                    "Symlink is not allowed for the evidence destination."
                ) from exc
            raise

    created = False
    try:
        descriptor = open_destination()
    except FileNotFoundError:
        try:
            os.mkdir(destination_name, 0o2750, dir_fd=parent_descriptor)
            created = True
        except FileExistsError:
            pass
        descriptor = open_destination()

    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Evidence destination is not a directory.")
        if created:
            if os.geteuid() == 0:
                os.fchown(descriptor, 0, gid)
            elif gid != os.getegid():
                raise ValueError(
                    "A non-root migration process can only create evidence "
                    "for its effective group."
                )
            os.fchmod(descriptor, 0o2750)
        else:
            expected_uid = 0 if os.geteuid() == 0 else os.geteuid()
            mode = stat.S_IMODE(info.st_mode)
            if (
                info.st_uid != expected_uid
                or info.st_gid != gid
                or mode != 0o2750
            ):
                raise ValueError(
                    "Existing evidence destination must be owned by the "
                    "expected owner/group and have mode 2750; it was not "
                    "changed."
                )
        return descriptor, created
    except BaseException:
        os.close(descriptor)
        if created:
            try:
                os.rmdir(destination_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        raise


def migrate_evidence(
    source: Path,
    destination: Path,
    gid: int,
) -> tuple[list[str], list[str]]:
    if gid < 0:
        raise ValueError("gid must be non-negative.")
    if os.geteuid() != 0 and gid != os.getegid():
        raise ValueError(
            "A non-root migration process can only write files for its "
            "effective group."
        )

    source = _absolute_path(source)
    destination = _absolute_path(destination)
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Source and destination evidence trees must not overlap.")

    source_descriptor = _open_directory(source)
    parent_descriptor = -1
    destination_descriptor = -1
    destination_created = False
    imported: list[str] = []
    conflicts: list[str] = []
    destination_name = destination.name
    try:
        source_info = os.fstat(source_descriptor)
        if not stat.S_ISDIR(source_info.st_mode):
            raise ValueError(f"Source is not a directory: {source}")
        parent_descriptor = _open_directory(destination.parent)
        destination_descriptor, destination_created = _secure_destination(
            parent_descriptor,
            destination_name,
            gid,
        )

        for name in sorted(os.listdir(source_descriptor)):
            if EVIDENCE_NAME.fullmatch(name) is None:
                continue
            try:
                source_file = os.open(name, _FILE_FLAGS, dir_fd=source_descriptor)
            except FileNotFoundError:
                continue
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.EINVAL):
                    continue
                raise

            try:
                info = os.fstat(source_file)
                if not stat.S_ISREG(info.st_mode):
                    continue
                temporary_name = f".{name}.{secrets.token_hex(12)}.tmp"
                output_descriptor = os.open(
                    temporary_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=destination_descriptor,
                )
                try:
                    with os.fdopen(source_file, "rb", closefd=False) as input_file:
                        with os.fdopen(output_descriptor, "wb", closefd=False) as output_file:
                            shutil.copyfileobj(input_file, output_file)
                            output_file.flush()
                            os.fsync(output_file.fileno())
                    copied_info = os.fstat(source_file)
                    if (
                        info.st_dev,
                        info.st_ino,
                        info.st_size,
                        info.st_mtime_ns,
                        info.st_ctime_ns,
                    ) != (
                        copied_info.st_dev,
                        copied_info.st_ino,
                        copied_info.st_size,
                        copied_info.st_mtime_ns,
                        copied_info.st_ctime_ns,
                    ):
                        raise OSError(
                            errno.EBUSY,
                            f"Source evidence changed while being copied: {name}",
                        )
                    if os.geteuid() == 0:
                        os.fchown(output_descriptor, 0, gid)
                    os.fchmod(output_descriptor, 0o640)
                except BaseException:
                    os.close(output_descriptor)
                    try:
                        os.unlink(temporary_name, dir_fd=destination_descriptor)
                    except FileNotFoundError:
                        pass
                    raise
                else:
                    os.close(output_descriptor)

                try:
                    os.link(
                        temporary_name,
                        name,
                        src_dir_fd=destination_descriptor,
                        dst_dir_fd=destination_descriptor,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    conflicts.append(str(destination / name))
                else:
                    imported.append(str(destination / name))
                    os.fsync(destination_descriptor)
                finally:
                    try:
                        os.unlink(temporary_name, dir_fd=destination_descriptor)
                    except FileNotFoundError:
                        pass
            except OSError as exc:
                raise EvidenceMigrationError(
                    f"Could not import {name}: {exc}",
                    imported,
                ) from exc
            finally:
                os.close(source_file)
    except BaseException:
        if destination_created and not imported and destination_descriptor >= 0:
            try:
                os.rmdir(destination_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        raise
    finally:
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        os.close(source_descriptor)
    return conflicts, imported


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--gid", type=int, required=True)
    args = parser.parse_args()
    try:
        conflicts, imported = migrate_evidence(
            args.source,
            args.destination,
            args.gid,
        )
    except (OSError, ValueError) as exc:
        for target in getattr(exc, "imported", ()):
            print(f"IMPORTED: {target}")
        print(f"Migration failed: {exc}", file=sys.stderr)
        if getattr(exc, "imported", ()):
            print(
                "Some files were imported before the failure; preserve them "
                "and inspect the destination before retrying.",
                file=sys.stderr,
            )
        return 2
    for target in conflicts:
        print(f"CONFLICT: existing evidence preserved: {target}", file=sys.stderr)
    for target in imported:
        print(f"IMPORTED: {target}")
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
