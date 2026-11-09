from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import queue
import threading
from typing import AsyncIterator
from uuid import UUID, uuid4

from backend.api.schemas import (
    ExecutionEvent,
    ExecutionEventName,
)
from backend.api.services.worker_client import call_worker
from backend.models.canonical_intent import CanonicalIntent


class ExecutionBusyError(RuntimeError):
    pass


class ExecutionManager:
    def __init__(self, worker_call_fn=call_worker) -> None:
        self._worker_call = worker_call_fn
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="intentflow-execution",
        )
        self._lock = threading.Lock()
        self._records: dict[str, list[ExecutionEvent]] = {}
        self._listeners: dict[str, list[queue.Queue[ExecutionEvent]]] = {}
        self._active_execution_id: str | None = None
        self._statuses: dict[str, str] = {}
        self._intents: dict[str, CanonicalIntent] = {}
        self._accepted_at: dict[str, datetime] = {}

    @property
    def active_status(self) -> str:
        with self._lock:
            if self._active_execution_id is None:
                return "IDLE"
            return self._statuses.get(self._active_execution_id, "RUNNING")

    def is_busy(self) -> bool:
        with self._lock:
            return self._active_execution_id is not None

    def execution_status(
        self,
        execution_id: str,
    ) -> tuple[str, list[ExecutionEvent]] | None:
        with self._lock:
            if execution_id not in self._records:
                return None
            return (
                self._statuses.get(execution_id, "RUNNING"),
                list(self._records[execution_id]),
            )

    def submit(self, intent: CanonicalIntent) -> tuple[UUID, datetime]:
        execution_uuid = uuid4()
        execution_id = execution_uuid.hex
        accepted_at = datetime.now(timezone.utc)
        with self._lock:
            if self._active_execution_id is not None:
                raise ExecutionBusyError(
                    f"Execution {self._active_execution_id} is already running."
                )
            self._active_execution_id = execution_id
            self._statuses[execution_id] = "RUNNING"
            self._records[execution_id] = []
            self._intents[execution_id] = intent
            self._accepted_at[execution_id] = accepted_at
            self._emit_locked(
                ExecutionEventName.EXECUTION_ACCEPTED,
                execution_id,
                accepted_at,
                "Validated canonical intent accepted for asynchronous execution.",
            )
        self._executor.submit(self._run, intent, execution_id)
        return execution_uuid, accepted_at

    def _run(self, intent: CanonicalIntent, execution_id: str) -> None:
        self._emit(
            ExecutionEventName.EXECUTION_RUNNING,
            execution_id,
            "The privileged worker is starting the live SDN execution.",
        )
        try:
            result = self._worker_call(
                "execute",
                intent=intent,
                execution_id=execution_id,
                timeout_s=900,
            )
            status = result.get("execution_status")
            if not isinstance(status, str) or not status:
                raise RuntimeError("The SDN worker returned no execution status.")
            if result.get("execution_id") != execution_id:
                raise RuntimeError("The SDN worker returned a mismatched execution ID.")
            event = {
                "SUCCEEDED": ExecutionEventName.EXECUTION_SUCCEEDED,
                "FAILED": ExecutionEventName.EXECUTION_FAILED,
            }.get(status, ExecutionEventName.EXECUTION_COMPLETED)
            detail = f"Execution finished with status {status}."
            with self._lock:
                self._statuses[execution_id] = status
                self._emit_locked(event, execution_id, datetime.now(timezone.utc), detail)
        except Exception as exc:
            with self._lock:
                self._statuses[execution_id] = "FAILED"
                self._emit_locked(
                    ExecutionEventName.EXECUTION_FAILED,
                    execution_id,
                    datetime.now(timezone.utc),
                    f"{type(exc).__name__}: {exc}",
                )
        finally:
            with self._lock:
                if self._active_execution_id == execution_id:
                    self._active_execution_id = None

    def _emit(
        self,
        event: ExecutionEventName,
        execution_id: str,
        detail: str,
    ) -> None:
        with self._lock:
            self._emit_locked(event, execution_id, datetime.now(timezone.utc), detail)

    def _emit_locked(
        self,
        event: ExecutionEventName,
        execution_id: str,
        timestamp: datetime,
        detail: str | None,
    ) -> None:
        record = ExecutionEvent(
            execution_id=execution_id,
            event=event,
            timestamp=timestamp,
            detail=detail,
        )
        self._records.setdefault(execution_id, []).append(record)
        for listener in self._listeners.get(execution_id, []):
            listener.put_nowait(record)

    async def stream_events(self, execution_id: str) -> AsyncIterator[ExecutionEvent]:
        listener: queue.Queue[ExecutionEvent] = queue.Queue()
        with self._lock:
            events = self._records.get(execution_id)
            if events is None:
                raise KeyError(execution_id)
            initial_events = list(events)
            self._listeners.setdefault(execution_id, []).append(listener)
        try:
            for event in initial_events:
                yield event
                if event.event in {
                    ExecutionEventName.EXECUTION_SUCCEEDED,
                    ExecutionEventName.EXECUTION_COMPLETED,
                    ExecutionEventName.EXECUTION_FAILED,
                }:
                    return
            while True:
                try:
                    event = await asyncio.to_thread(listener.get, True, 20)
                except queue.Empty:
                    with self._lock:
                        terminal = self._statuses.get(execution_id) not in (None, "RUNNING")
                    if terminal:
                        return
                    continue
                yield event
                if event.event in {
                    ExecutionEventName.EXECUTION_SUCCEEDED,
                    ExecutionEventName.EXECUTION_COMPLETED,
                    ExecutionEventName.EXECUTION_FAILED,
                }:
                    return
        finally:
            with self._lock:
                listeners = self._listeners.get(execution_id, [])
                if listener in listeners:
                    listeners.remove(listener)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
