from __future__ import annotations

import sqlite3
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

from app.models import Generation

SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    duration INTEGER NOT NULL,
    resolution TEXT NOT NULL,
    generate_audio INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    image_media_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    remote_id TEXT,
    video_url TEXT,
    local_video_path TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_generations_created ON generations(created_at DESC);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def from_row(row: sqlite3.Row) -> Generation:
    values = dict(row)
    for field in fields(Generation):
        if field.type in {"bool", bool} and values[field.name] is not None:
            values[field.name] = bool(values[field.name])
    return Generation(**values)


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def insert(self, job: Generation) -> None:
        with self.connect() as connection:
            connection.execute("""
                INSERT INTO generations (id, model, prompt, duration, resolution, generate_audio,
                    image_path, image_media_type, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (job.id, job.model, job.prompt, job.duration, job.resolution, int(job.generate_audio),
                  job.image_path, job.image_media_type, job.status, job.created_at, job.updated_at))

    def get(self, job_id: str) -> Generation | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM generations WHERE id = ?", (job_id,)).fetchone()
        return from_row(row) if row else None

    def list(self, limit: int = 40) -> list[Generation]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM generations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [Generation(**dict(row)) for row in rows]

    def unfinished(self) -> list[Generation]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM generations WHERE status IN ('queued', 'running')").fetchall()
        return [Generation(**dict(row)) for row in rows]

    def update(self, job_id: str, **values) -> None:
        allowed = {"status", "remote_id", "video_url", "local_video_path", "error"}
        if not values or not set(values) <= allowed:
            raise ValueError("Invalid generation update")
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.connect() as connection:
            connection.execute(f"UPDATE generations SET {assignments} WHERE id = ?", (*values.values(), job_id))

    def clear(self) -> list[tuple[str | None, str | None]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT image_path, local_video_path FROM generations").fetchall()
            connection.execute("DELETE FROM generations")
        return [(row[0], row[1]) for row in rows]
