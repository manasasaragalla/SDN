#!/usr/bin/env python3
"""Reject dependency lock entries without exact pins and SHA-256 hashes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_FILES = (
    ROOT / "requirements.txt",
    ROOT / "scripts" / "ryu-requirements.txt",
)
SOURCE_FILES = (
    ROOT / "requirements.in",
    ROOT / "scripts" / "ryu-requirements.in",
)
REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?=="
    r"[A-Za-z0-9][A-Za-z0-9.!+_-]*(?:\s*;.*)?(?:\s*\\)?$"
)
HASH = re.compile(r"^\s*--hash=sha256:[0-9a-f]{64}\s*\\?$")
RYU_SOURCE = re.compile(r"^([0-9a-f]{64})\s+ryu-4\.34\.tar\.gz$")
RYU_REQUIRED_DISTRIBUTIONS = {
    "eventlet",
    "msgpack",
    "netaddr",
    "oslo-config",
    "ovs",
    "routes",
    "six",
    "tinyrpc",
    "webob",
    "pbr",
    "setuptools",
    "wheel",
}


def _validate_lock(path: Path) -> list[str]:
    errors: list[str] = []
    current: str | None = None
    hashes = 0
    lines = path.read_text(encoding="utf-8").splitlines()

    def finish(line_number: int) -> None:
        if current is not None and hashes == 0:
            errors.append(f"{path}:{line_number}: {current} has no SHA-256 hash")

    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash="):
            if current is None or not HASH.fullmatch(line):
                errors.append(f"{path}:{line_number}: malformed or orphaned hash")
            else:
                hashes += 1
            continue
        finish(line_number - 1)
        current = line
        hashes = 0
        if not REQUIREMENT.fullmatch(line):
            errors.append(
                f"{path}:{line_number}: dependency must use an exact == pin "
                "and continue with SHA-256 hashes"
            )

    finish(len(lines))
    if current is None:
        errors.append(f"{path}: no dependency entries found")
    return errors


def _validate_source(path: Path) -> list[str]:
    errors: list[str] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not REQUIREMENT.fullmatch(line):
            errors.append(
                f"{path}:{line_number}: dependency source must use an exact == pin"
            )
    return errors


def _distribution_versions(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(
            r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)",
            line,
        )
        if match:
            name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
            versions[name] = match.group(2)
    return versions


def main() -> int:
    errors: list[str] = []
    for path in SOURCE_FILES:
        if not path.is_file():
            errors.append(f"{path}: dependency source is missing")
        else:
            errors.extend(_validate_source(path))
    for source_path, lock_path in zip(SOURCE_FILES, LOCK_FILES):
        if source_path.is_file() and lock_path.is_file():
            source_versions = _distribution_versions(source_path)
            lock_versions = _distribution_versions(lock_path)
            missing = source_versions.keys() - lock_versions.keys()
            if missing:
                errors.append(
                    f"{lock_path}: missing pinned source dependencies: "
                    + ", ".join(sorted(missing))
                )
            mismatched = {
                name: (version, lock_versions[name])
                for name, version in source_versions.items()
                if name in lock_versions and lock_versions[name] != version
            }
            if mismatched:
                details = ", ".join(
                    f"{name} source={source_version} lock={lock_version}"
                    for name, (source_version, lock_version) in sorted(
                        mismatched.items()
                    )
                )
                errors.append(f"{lock_path}: source/lock versions differ: {details}")

    ryu_source = ROOT / "scripts" / "ryu-requirements.in"
    if ryu_source.is_file():
        ryu_source_versions = _distribution_versions(ryu_source)
        missing = RYU_REQUIRED_DISTRIBUTIONS - ryu_source_versions.keys()
        if missing:
            errors.append(
                f"{ryu_source}: missing pinned Ryu runtime/build dependencies: "
                + ", ".join(sorted(missing))
            )
        ryu_lock_path = ROOT / "scripts" / "ryu-requirements.txt"
        ryu_lock_versions = (
            _distribution_versions(ryu_lock_path)
            if ryu_lock_path.is_file()
            else {}
        )
        missing_lock = RYU_REQUIRED_DISTRIBUTIONS - ryu_lock_versions.keys()
        if missing_lock:
            errors.append(
                f"{ryu_lock_path}: missing hash-locked "
                "Ryu runtime/build dependencies: "
                + ", ".join(sorted(missing_lock))
            )
        elif ryu_source.is_file():
            mismatched = {
                name: (version, ryu_lock_versions[name])
                for name, version in ryu_source_versions.items()
                if name in ryu_lock_versions and ryu_lock_versions[name] != version
            }
            if mismatched:
                details = ", ".join(
                    f"{name} source={source_version} lock={lock_version}"
                    for name, (source_version, lock_version) in sorted(
                        mismatched.items()
                    )
                )
                errors.append(
                    f"{ryu_lock_path}: source/lock versions differ: {details}"
                )
    for path in LOCK_FILES:
        if not path.is_file():
            errors.append(f"{path}: lock file is missing")
        else:
            errors.extend(_validate_lock(path))

    source_lock = ROOT / "scripts" / "ryu-4.34.sha256"
    try:
        lines = source_lock.read_text(encoding="ascii").splitlines()
    except OSError as exc:
        errors.append(f"{source_lock}: cannot read source digest: {exc}")
    else:
        if len(lines) != 1 or not RYU_SOURCE.fullmatch(lines[0]):
            errors.append(
                f"{source_lock}: expected one SHA-256 digest for ryu-4.34.tar.gz"
            )

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Dependency lock validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
