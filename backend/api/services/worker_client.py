from __future__ import annotations

import json
import os
import socket
from uuid import uuid4

from backend.api.schemas import WorkerRequest, WorkerResponse
from backend.models.canonical_intent import CanonicalIntent

MAX_WORKER_RESPONSE_BYTES = 2 * 1024 * 1024


class WorkerUnavailableError(RuntimeError):
    pass


class WorkerProtocolError(RuntimeError):
    pass


def worker_socket_path() -> str:
    return os.environ.get(
        "INTENTFLOW_WORKER_SOCKET",
        "/run/intentflow/worker.sock",
    )


def call_worker(
    operation: str,
    *,
    intent: CanonicalIntent | None = None,
    execution_id: str | None = None,
    timeout_s: float = 900,
    socket_path: str | None = None,
) -> dict:
    request = WorkerRequest(
        request_id=uuid4(),
        operation=operation,
        intent=intent,
        execution_id=execution_id,
    )
    encoded = request.model_dump_json().encode("utf-8") + b"\n"
    path = socket_path or worker_socket_path()

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout_s)
            connection.connect(path)
            connection.sendall(encoded)
            response_bytes = bytearray()
            while len(response_bytes) <= MAX_WORKER_RESPONSE_BYTES:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                response_bytes.extend(chunk)
                if b"\n" in chunk:
                    break
    except (OSError, TimeoutError) as exc:
        raise WorkerUnavailableError(
            "The privileged SDN worker is unavailable or did not respond."
        ) from exc

    if len(response_bytes) > MAX_WORKER_RESPONSE_BYTES:
        raise WorkerProtocolError("The SDN worker response exceeded the size limit.")
    line = bytes(response_bytes).split(b"\n", 1)[0]
    try:
        response = WorkerResponse.model_validate_json(line)
    except Exception as exc:
        raise WorkerProtocolError("The SDN worker returned an invalid response.") from exc
    if response.request_id != request.request_id:
        raise WorkerProtocolError("The SDN worker response ID did not match the request.")
    if not response.ok:
        raise WorkerProtocolError(response.error or "The SDN worker operation failed.")
    return response.result or {}


def encode_worker_response(response: WorkerResponse) -> bytes:
    return json.dumps(
        response.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
