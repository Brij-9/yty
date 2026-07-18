from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.init()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    spec TEXT NOT NULL,
                    artifacts TEXT NOT NULL DEFAULT '{}',
                    output_path TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
            if "artifacts" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN artifacts TEXT NOT NULL DEFAULT '{}'")

    def create(self, spec: dict) -> dict:
        job_id = str(uuid.uuid4())
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id,status,progress,spec,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (job_id, "queued", 0, json.dumps(spec), now, now),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._serialize(row) if row else None

    def list(self, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._serialize(row) for row in rows]

    def claim_next(self) -> dict | None:
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                conn.commit()
                return None
            now = utcnow()
            conn.execute("UPDATE jobs SET status='running',progress=1,updated_at=? WHERE id=?", (now, row["id"]))
            conn.commit()
        return self.get(row["id"])

    def update(self, job_id: str, *, status: str | None = None, progress: int | None = None,
               output_path: str | None = None, error: str | None = None,
               artifacts: dict | None = None) -> dict:
        fields = ["updated_at=?"]
        values: list[object] = [utcnow()]
        for key, value in (("status", status), ("progress", progress), ("output_path", output_path), ("error", error)):
            if value is not None:
                fields.append(f"{key}=?")
                values.append(value)
        if artifacts is not None:
            fields.append("artifacts=?")
            values.append(json.dumps(artifacts))
        values.append(job_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {','.join(fields)} WHERE id=?", values)
        return self.get(job_id)

    def cancel(self, job_id: str) -> dict | None:
        job = self.get(job_id)
        if not job:
            return None
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        return self.update(job_id, status="cancelled")

    def retry(self, job_id: str) -> dict | None:
        job = self.get(job_id)
        if not job:
            return None
        if job["status"] not in {"failed", "cancelled"}:
            return job
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET status='queued',progress=0,error=NULL,updated_at=? WHERE id=?",
                (utcnow(), job_id),
            )
        return self.get(job_id)

    def recover_interrupted(self) -> int:
        with self.connect() as conn:
            result = conn.execute(
                "UPDATE jobs SET status='queued',updated_at=? WHERE status='running'",
                (utcnow(),),
            )
            return result.rowcount

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict:
        result = dict(row)
        result["spec"] = json.loads(result["spec"])
        result["artifacts"] = json.loads(result.get("artifacts") or "{}")
        return result
