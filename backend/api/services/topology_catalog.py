"""SQLite-backed catalog for saved, user-authored DESIGN topologies."""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator
from uuid import UUID, uuid4

from backend.models.topology_definition import (
    TopologyCatalogItem,
    TopologyDefinition,
    TopologyDefinitionInput,
    TopologyMode,
)


class TopologyCatalogError(RuntimeError):
    pass


class TopologyNotFoundError(TopologyCatalogError):
    pass


class TopologyVersionConflictError(TopologyCatalogError):
    pass


def default_catalog_path() -> Path:
    configured = os.environ.get("INTENTFLOW_TOPOLOGY_DB")
    if configured:
        return Path(configured)
    state_home = Path(
        os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
    )
    return state_home / "intentflow" / "topologies.sqlite3"


class TopologyCatalog:
    """Append-only topology versions with a single explicitly active version."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_catalog_path()

    def list(self) -> list[TopologyCatalogItem]:
        with self._connect() as connection:
            active = connection.execute(
                "SELECT topology_id, version FROM active_topology WHERE singleton = 1"
            ).fetchone()
            rows = connection.execute(
                """
                SELECT t.topology_id, t.version, t.name, t.mode, t.graph_json,
                       t.updated_at
                FROM topology_versions AS t
                JOIN (
                    SELECT topology_id, MAX(version) AS version
                    FROM topology_versions GROUP BY topology_id
                ) AS latest
                  ON latest.topology_id = t.topology_id
                 AND latest.version = t.version
                ORDER BY t.updated_at DESC, t.name COLLATE NOCASE
                """
            ).fetchall()
        return [
            TopologyCatalogItem(
                id=UUID(row["topology_id"]),
                name=row["name"],
                version=row["version"],
                mode=TopologyMode(row["mode"]),
                active=(
                    active is not None
                    and active["topology_id"] == row["topology_id"]
                    and active["version"] == row["version"]
                ),
                node_count=_node_count(row["graph_json"]),
                link_count=len(json.loads(row["graph_json"])["links"]),
                updated_at=_parse_datetime(row["updated_at"]),
            )
            for row in rows
        ]

    def get(self, topology_id: UUID, version: int | None = None) -> TopologyDefinition:
        with self._connect() as connection:
            row = self._fetch_version(connection, topology_id, version)
        if row is None:
            raise TopologyNotFoundError(f"Topology {topology_id} was not found.")
        return _definition_from_row(row)

    def versions(self, topology_id: UUID) -> list[TopologyDefinition]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM topology_versions
                WHERE topology_id = ? ORDER BY version DESC
                """,
                (str(topology_id),),
            ).fetchall()
        if not rows:
            raise TopologyNotFoundError(f"Topology {topology_id} was not found.")
        return [_definition_from_row(row) for row in rows]

    def active(self) -> TopologyDefinition | None:
        with self._connect() as connection:
            active = connection.execute(
                "SELECT topology_id, version FROM active_topology WHERE singleton = 1"
            ).fetchone()
            if active is None:
                return None
            row = self._fetch_version(
                connection,
                UUID(active["topology_id"]),
                active["version"],
            )
        return _definition_from_row(row) if row is not None else None

    def create(self, definition: TopologyDefinitionInput) -> TopologyDefinition:
        topology_id = uuid4()
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO topology_versions
                    (topology_id, version, name, mode, graph_json, positions_json,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _serialized_row(topology_id, 1, definition, now, now),
            )
        return self.get(topology_id, 1)

    def update(
        self,
        topology_id: UUID,
        expected_version: int,
        definition: TopologyDefinitionInput,
    ) -> TopologyDefinition:
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = self._latest_version(connection, topology_id)
            if latest is None:
                raise TopologyNotFoundError(f"Topology {topology_id} was not found.")
            if latest != expected_version:
                raise TopologyVersionConflictError(
                    f"Topology changed: expected version {expected_version}, "
                    f"current version is {latest}."
                )
            created_at = connection.execute(
                """
                SELECT created_at FROM topology_versions
                WHERE topology_id = ? AND version = 1
                """,
                (str(topology_id),),
            ).fetchone()["created_at"]
            version = latest + 1
            connection.execute(
                """
                INSERT INTO topology_versions
                    (topology_id, version, name, mode, graph_json, positions_json,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _serialized_row(
                    topology_id,
                    version,
                    definition,
                    created_at,
                    now,
                ),
            )
            active = connection.execute(
                "SELECT topology_id, version FROM active_topology WHERE singleton = 1"
            ).fetchone()
            if active and active["topology_id"] == str(topology_id):
                connection.execute(
                    "UPDATE active_topology SET version = ? WHERE singleton = 1",
                    (version,),
                )
        return self.get(topology_id, version)

    def rename(
        self,
        topology_id: UUID,
        expected_version: int,
        name: str,
    ) -> TopologyDefinition:
        current = self.get(topology_id)
        return self.update(
            topology_id,
            expected_version,
            TopologyDefinitionInput(
                name=name,
                mode=current.mode,
                graph=current.graph,
                positions=current.positions,
            ),
        )

    def duplicate(
        self,
        topology_id: UUID,
        name: str | None = None,
    ) -> TopologyDefinition:
        current = self.get(topology_id)
        return self.create(
            TopologyDefinitionInput(
                name=name or f"{current.name} copy",
                mode=TopologyMode.DESIGN,
                graph=current.graph,
                positions=current.positions,
            )
        )

    def activate(self, topology_id: UUID, version: int | None = None) -> TopologyDefinition:
        definition = self.get(topology_id, version)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO active_topology(singleton, topology_id, version)
                VALUES (1, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    topology_id = excluded.topology_id,
                    version = excluded.version
                """,
                (str(topology_id), definition.version),
            )
        return definition

    def deactivate(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM active_topology WHERE singleton = 1")

    def delete(self, topology_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._latest_version(connection, topology_id) is None:
                raise TopologyNotFoundError(f"Topology {topology_id} was not found.")
            connection.execute(
                "DELETE FROM active_topology WHERE singleton = 1 AND topology_id = ?",
                (str(topology_id),),
            )
            connection.execute(
                "DELETE FROM topology_versions WHERE topology_id = ?",
                (str(topology_id),),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS topology_versions (
                    topology_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    name TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK (mode = 'DESIGN'),
                    graph_json TEXT NOT NULL,
                    positions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (topology_id, version)
                );
                CREATE TABLE IF NOT EXISTS active_topology (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    topology_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    FOREIGN KEY (topology_id, version)
                        REFERENCES topology_versions(topology_id, version)
                        ON DELETE CASCADE
                );
                """
            )
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _latest_version(
        connection: sqlite3.Connection,
        topology_id: UUID,
    ) -> int | None:
        row = connection.execute(
            """
            SELECT MAX(version) AS version FROM topology_versions
            WHERE topology_id = ?
            """,
            (str(topology_id),),
        ).fetchone()
        return row["version"] if row is not None else None

    @classmethod
    def _fetch_version(
        cls,
        connection: sqlite3.Connection,
        topology_id: UUID,
        version: int | None,
    ) -> sqlite3.Row | None:
        if version is None:
            version = cls._latest_version(connection, topology_id)
        if version is None:
            return None
        return connection.execute(
            """
            SELECT * FROM topology_versions
            WHERE topology_id = ? AND version = ?
            """,
            (str(topology_id), version),
        ).fetchone()


def _serialized_row(
    topology_id: UUID,
    version: int,
    definition: TopologyDefinitionInput,
    created_at: str,
    updated_at: str,
) -> tuple[str, int, str, str, str, str, str, str]:
    return (
        str(topology_id),
        version,
        definition.name,
        definition.mode.value,
        definition.graph.model_dump_json(),
        json.dumps(
            {
                name: position.model_dump(mode="json")
                for name, position in definition.positions.items()
            },
            sort_keys=True,
        ),
        created_at,
        updated_at,
    )


def _definition_from_row(row: sqlite3.Row) -> TopologyDefinition:
    return TopologyDefinition(
        id=UUID(row["topology_id"]),
        version=row["version"],
        name=row["name"],
        mode=row["mode"],
        graph=json.loads(row["graph_json"]),
        positions=json.loads(row["positions_json"]),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )


def _node_count(graph_json: str) -> int:
    graph = json.loads(graph_json)
    return len(graph["switches"]) + len(graph["hosts"])


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
