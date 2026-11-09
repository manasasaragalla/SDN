from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import errno
import fcntl
import logging
import os
import signal
import socket
import stat
import struct
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.api.schemas import WorkerRequest, WorkerResponse
from backend.api.services.worker_client import encode_worker_response

LOGGER = logging.getLogger("intentflow.worker")
MAX_REQUEST_BYTES = 64 * 1024
RYU_STARTUP_TIMEOUT_S = 60.0
TOPOLOGY_DISCOVERY_TIMEOUT_S = 30.0
RYU_BASE_URL = "http://127.0.0.1:8080"
WORKER_LOCK_PATH = Path("/run/intentflow/worker.lock")


def _read_request(connection: socket.socket) -> WorkerRequest:
    data = bytearray()
    while len(data) <= MAX_REQUEST_BYTES:
        chunk = connection.recv(min(4096, MAX_REQUEST_BYTES + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break
    if len(data) > MAX_REQUEST_BYTES:
        raise ValueError("Worker request exceeded the size limit.")
    line = bytes(data).split(b"\n", 1)[0]
    return WorkerRequest.model_validate_json(line)


def _peer_is_allowed(connection: socket.socket, allowed_gid: int) -> bool:
    if not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("Unix peer credentials are required on this platform.")
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    _pid, _uid, gid = struct.unpack("3i", credentials)
    return gid == allowed_gid


def _handle_operation(request: WorkerRequest) -> dict[str, Any]:
    if request.operation == "health":
        return {"ready": True, "checked_at": datetime.now(timezone.utc).isoformat()}
    if request.operation == "topology":
        return _discover_topology()
    if request.operation == "execute":
        return _execute_intent(request)
    raise ValueError("Unsupported worker operation.")


def _discover_topology() -> dict[str, Any]:
    from mininet.log import setLogLevel

    from backend.decision.topology_graph import build_from_mininet
    from testbed.topology.diamond import build_diamond_topology, start as start_topology

    setLogLevel("warning")
    ryu_process = _start_ryu()
    net = None
    try:
        net = build_diamond_topology()
        start_topology(net)
        graph = build_from_mininet(net)
        snapshot = _wait_for_topology_snapshot(graph)
        return {
            "graph": graph.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
            "topology_fingerprint": snapshot.topology_fingerprint,
        }
    finally:
        try:
            if net is not None:
                net.stop()
        finally:
            _stop_ryu(ryu_process)


def _execute_intent(request: WorkerRequest) -> dict[str, Any]:
    from mininet.log import setLogLevel

    from backend.capabilities import ExecutionMode, resolve_capabilities
    from backend.decision.topology_graph import build_from_mininet
    from backend.orchestration.generalized_constraints import (
        run_generalized_constraint_demo,
    )
    from backend.orchestration.generalized_latency import read_live_topology_snapshot
    from testbed.topology.diamond import build_diamond_topology, start as start_topology

    if request.intent is None or request.execution_id is None:
        raise ValueError("An intent and execution ID are required for execution.")
    if request.intent.requested_actions:
        raise ValueError(
            "Requested actions are not supported by this execution pipeline."
        )

    setLogLevel("warning")
    ryu_process = _start_ryu()
    net = None
    try:
        net = build_diamond_topology()
        start_topology(net)
        graph = build_from_mininet(net)
        snapshot = _wait_for_topology_snapshot(graph)
        capabilities = resolve_capabilities(
            request.intent,
            graph,
            execution_mode=ExecutionMode.GENERALIZED,
        )
        if capabilities.eligibility.status.value != "CAPABILITY_READY":
            raise ValueError(
                "Intent is not executable: "
                + "; ".join(capabilities.eligibility.reasons)
            )
        scope = request.intent.scope
        if scope.source not in net.nameToNode or scope.destination not in net.nameToNode:
            raise ValueError("Intent endpoints are not present in the discovered topology.")

        result = run_generalized_constraint_demo(
            graph,
            net.get(scope.source),
            net.get(scope.destination),
            request.intent,
            snapshot,
            fresh_snapshot_provider=lambda: read_live_topology_snapshot(graph),
            execution_id=request.execution_id,
        )
        return {
            "execution_id": request.execution_id,
            "execution_status": result.status.value,
            "evidence_json_path": result.evidence_json_path,
            "evidence_markdown_path": result.evidence_markdown_path,
        }
    finally:
        try:
            if net is not None:
                net.stop()
        finally:
            _stop_ryu(ryu_process)


def _wait_for_topology_snapshot(graph):
    from backend.orchestration.generalized_latency import (
        LiveSnapshotError,
        read_live_topology_snapshot,
    )

    deadline = time.monotonic() + TOPOLOGY_DISCOVERY_TIMEOUT_S
    last_error: LiveSnapshotError | None = None
    while time.monotonic() < deadline:
        try:
            return read_live_topology_snapshot(graph, RYU_BASE_URL)
        except LiveSnapshotError as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Ryu topology snapshot unavailable: {last_error}")


def _start_ryu() -> Any:
    from backend.cli import OFP_PORT, RYU_MANAGER, WSAPI_PORT

    for port in (OFP_PORT, WSAPI_PORT):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(f"Required local Ryu port {port} is already in use.") from exc

    import subprocess

    process = subprocess.Popen(
        _ryu_command(RYU_MANAGER, OFP_PORT, WSAPI_PORT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    deadline = time.monotonic() + RYU_STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Ryu exited before becoming ready.")
        if _loopback_listeners_ready(process.pid, (OFP_PORT, WSAPI_PORT)):
            try:
                with socket.create_connection(("127.0.0.1", WSAPI_PORT), timeout=0.25):
                    return process
            except OSError:
                pass
        time.sleep(0.2)
    _stop_ryu(process)
    raise RuntimeError(
        "Ryu did not start both OpenFlow and REST listeners on loopback "
        "before the startup deadline."
    )


def _ryu_command(ryu_manager: Path, ofp_port: int, wsapi_port: int) -> list[str]:
    return [
        str(ryu_manager),
        "ryu.app.ofctl_rest",
        "--ofp-listen-host",
        "127.0.0.1",
        "--ofp-tcp-listen-port",
        str(ofp_port),
        "--wsapi-host",
        "127.0.0.1",
        "--wsapi-port",
        str(wsapi_port),
    ]


def _loopback_listeners_ready(pid: int, expected_ports: tuple[int, ...]) -> bool:
    try:
        owned_inodes = _process_socket_inodes(pid)
        tcp_contents = Path(f"/proc/{pid}/net/tcp").read_text(encoding="ascii")
        tcp6_contents = Path(f"/proc/{pid}/net/tcp6").read_text(encoding="ascii")
    except OSError:
        return False
    if _has_listener_on_ports(tcp6_contents, expected_ports):
        return False
    return _loopback_listener_addresses(
        tcp_contents,
        expected_ports,
        owned_inodes,
    )


def _process_socket_inodes(pid: int) -> set[str]:
    inodes: set[str] = set()
    for descriptor in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(descriptor)
        except FileNotFoundError:
            continue
        if target.startswith("socket:[") and target.endswith("]"):
            inodes.add(target[8:-1])
    return inodes


def _loopback_listener_addresses(
    contents: str,
    expected_ports: tuple[int, ...],
    owned_inodes: set[str],
) -> bool:
    entries = _tcp_listener_entries(contents)
    matching = [entry for entry in entries if entry[1] in expected_ports]
    if {port for _, port, _ in matching} != set(expected_ports):
        return False
    if len(matching) != len(expected_ports):
        return False
    return all(
        address == "0100007F" and inode in owned_inodes
        for address, _, inode in matching
    )


def _tcp_listener_entries(contents: str) -> list[tuple[str, int, str]]:
    entries: list[tuple[str, int, str]] = []
    rows = contents.splitlines()[1:]
    for row in rows:
        fields = row.split()
        if len(fields) < 4 or fields[3] != "0A":
            continue
        try:
            address, port_hex = fields[1].split(":")
            port = int(port_hex, 16)
            inode = fields[9]
        except ValueError:
            continue
        except IndexError:
            continue
        entries.append((address.upper(), port, inode))
    return entries


def _has_listener_on_ports(contents: str, expected_ports: tuple[int, ...]) -> bool:
    return any(port in expected_ports for _, port, _ in _tcp_listener_entries(contents))


def _stop_ryu(process: Any) -> None:
    if process.poll() is not None:
        return
    import subprocess

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _respond(connection: socket.socket, request_id: uuid.UUID, result: dict | None, error: str | None) -> None:
    response = WorkerResponse(
        request_id=request_id,
        ok=error is None,
        result=result,
        error=error,
    )
    connection.sendall(encode_worker_response(response))


def serve(
    socket_path: str,
    allowed_gid: int,
    *,
    stop_event: threading.Event | None = None,
) -> None:
    if not _effective_root():
        raise RuntimeError("The SDN worker must run as root.")
    if not _trusted_worker_install():
        raise RuntimeError(
            "Refusing to start from a worker, interpreter, or Ryu path that is "
            "not root-owned and non-writable by group/other users. Install the "
            "worker under a protected root-owned directory."
        )
    path = Path(socket_path)
    if not path.is_absolute():
        raise ValueError("The worker socket path must be absolute.")
    if allowed_gid < 0:
        raise ValueError("The API group ID must be non-negative.")
    if not _worker_socket_directory_is_trusted(path.parent, allowed_gid) or not (
        _worker_socket_directory_is_trusted(WORKER_LOCK_PATH.parent, allowed_gid)
    ):
        raise RuntimeError(
            "The worker socket and lock directories must be root-owned, "
            "grouped to the API group, traversable by that group, and not "
            "writable by group or other users. Provision them before startup."
        )
    lock_file = _acquire_worker_lock()
    server: socket.socket | None = None
    owned_socket: tuple[int, int] | None = None
    try:
        _remove_stale_socket(path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        socket_info = path.lstat()
        owned_socket = (socket_info.st_dev, socket_info.st_ino)
        os.chown(path, 0, allowed_gid)
        os.chmod(path, 0o660)
        server.listen(8)
        server.settimeout(0.2)
        os.environ["INTENTFLOW_EVIDENCE_GID"] = str(allowed_gid)
        LOGGER.info("SDN worker listening on %s for group %s", path, allowed_gid)
        operation_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="intentflow-worker") as pool:
            while stop_event is None or not stop_event.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                pool.submit(_serve_connection, connection, allowed_gid, operation_lock)
    finally:
        try:
            if server is not None:
                server.close()
        finally:
            try:
                if owned_socket is not None:
                    _unlink_owned_socket(path, owned_socket)
            finally:
                os.close(lock_file)


def _effective_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _worker_socket_directory_is_trusted(path: Path, allowed_gid: int) -> bool:
    try:
        info = path.stat()
        mode = stat.S_IMODE(info.st_mode)
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == 0
        and info.st_gid == allowed_gid
        and mode & 0o050 == 0o050
        and mode & 0o020 == 0
        and mode & 0o007 == 0
        and _is_root_owned_and_not_group_writable(path)
    )


def _acquire_worker_lock(lock_path: Path | None = None) -> int:
    lock_path = lock_path or WORKER_LOCK_PATH
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("Worker lock path is not a regular file.")
        if os.geteuid() == 0:
            if info.st_uid != 0:
                raise RuntimeError("Worker lock file is not owned by root.")
            os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except BlockingIOError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise RuntimeError("Another SDN worker already owns the execution service.") from exc
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise RuntimeError(f"Could not acquire worker lock: {exc}") from exc
    except Exception:
        if "descriptor" in locals():
            os.close(descriptor)
        raise


def _remove_stale_socket(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(info.st_mode):
        raise RuntimeError("Refusing to replace a non-socket worker path.")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(0.2)
    try:
        probe.connect(str(path))
    except OSError as exc:
        if exc.errno not in (errno.ECONNREFUSED, errno.ENOENT):
            raise RuntimeError(
                f"Could not establish whether the existing worker socket is stale: {exc}"
            ) from exc
        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise RuntimeError("Worker socket changed while checking staleness.")
        path.unlink()
    else:
        raise RuntimeError("A live worker already owns the socket path.")
    finally:
        probe.close()


def _unlink_owned_socket(path: Path, identity: tuple[int, int]) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == identity:
        path.unlink()


def _trusted_worker_install() -> bool:
    from backend.cli import PROJECT_ROOT, RYU_MANAGER

    critical_paths = (PROJECT_ROOT, Path(__file__), Path(sys.executable), RYU_MANAGER)
    if not all(_is_root_owned_and_not_group_writable(path) for path in critical_paths):
        return False
    try:
        return all(
            _is_root_owned_and_not_group_writable(path)
            for path in PROJECT_ROOT.rglob("*")
        )
    except OSError:
        return False


def _is_root_owned_and_not_group_writable(path: Path) -> bool:
    try:
        current = path.resolve(strict=True)
        while True:
            info = current.stat()
            if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                return False
            if current.parent == current:
                return True
            current = current.parent
    except OSError:
        return False


def _serve_connection(
    connection: socket.socket,
    allowed_gid: int,
    operation_lock: threading.Lock,
) -> None:
    with connection:
        connection.settimeout(10)
        request = None
        try:
            if not _peer_is_allowed(connection, allowed_gid):
                raise PermissionError("Caller is not in the configured API group.")
            request = _read_request(connection)
            if request.operation == "health":
                result = _handle_operation(request)
                result["operation_busy"] = operation_lock.locked()
            elif operation_lock.acquire(blocking=False):
                try:
                    result = _handle_operation(request)
                finally:
                    operation_lock.release()
            else:
                raise RuntimeError("Another topology or execution operation is active.")
            _respond(connection, request.request_id, result, None)
        except (ValidationError, ValueError, PermissionError) as exc:
            _respond(
                connection,
                request.request_id if request else uuid.uuid4(),
                None,
                str(exc),
            )
        except Exception as exc:
            LOGGER.exception("Worker operation failed")
            _respond(
                connection,
                request.request_id if request else uuid.uuid4(),
                None,
                f"{type(exc).__name__}: {exc}",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the privileged IntentFlow worker.")
    parser.add_argument(
        "--socket",
        default=os.environ.get("INTENTFLOW_WORKER_SOCKET", "/run/intentflow/worker.sock"),
    )
    parser.add_argument(
        "--allowed-gid",
        type=int,
        default=os.environ.get("INTENTFLOW_API_GID"),
        required=os.environ.get("INTENTFLOW_API_GID") is None,
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stop_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop_event.set())
    serve(arguments.socket, arguments.allowed_gid, stop_event=stop_event)


if __name__ == "__main__":
    main()
