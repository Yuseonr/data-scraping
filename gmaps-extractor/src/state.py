import sqlite3
from pathlib import Path
from contextlib import contextmanager


class StateDB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                cell_id    TEXT NOT NULL,
                keyword    TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending',
                worker_id  INTEGER,
                started_at TEXT,
                finished_at TEXT,
                error      TEXT,
                PRIMARY KEY (cell_id, keyword)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

            CREATE TABLE IF NOT EXISTS seen_places (
                place_id TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS run_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self._conn.commit()

    def init_tasks(self, cell_ids: list[str], keywords: list[str]):
        """Populate task table, skip rows that already exist (safe for resume)."""
        cur = self._conn.cursor()
        for cell_id in cell_ids:
            for kw in keywords:
                cur.execute(
                    "INSERT OR IGNORE INTO tasks (cell_id, keyword) VALUES (?, ?)",
                    (cell_id, kw),
                )
        self._conn.commit()

    def claim_next(self, worker_id: int) -> tuple[str, str] | None:
        """Atomically claim one pending task, return (cell_id, keyword) or None."""
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        row = cur.execute(
            "SELECT cell_id, keyword FROM tasks WHERE status = 'pending' LIMIT 1"
        ).fetchone()
        if not row:
            self._conn.commit()
            return None
        cur.execute(
            "UPDATE tasks SET status = 'in_progress', worker_id = ?, started_at = datetime('now') "
            "WHERE cell_id = ? AND keyword = ?",
            (worker_id, row["cell_id"], row["keyword"]),
        )
        self._conn.commit()
        return (row["cell_id"], row["keyword"])

    def mark_done(self, cell_id: str, keyword: str):
        self._conn.execute(
            "UPDATE tasks SET status = 'done', finished_at = datetime('now') "
            "WHERE cell_id = ? AND keyword = ?",
            (cell_id, keyword),
        )
        self._conn.commit()

    def mark_failed(self, cell_id: str, keyword: str, error: str):
        self._conn.execute(
            "UPDATE tasks SET status = 'failed', finished_at = datetime('now'), error = ? "
            "WHERE cell_id = ? AND keyword = ?",
            (error, cell_id, keyword),
        )
        self._conn.commit()

    def release_stale(self, timeout_seconds: int = 600):
        """Reset in_progress tasks older than timeout back to pending."""
        self._conn.execute(
            "UPDATE tasks SET status = 'pending', worker_id = NULL "
            "WHERE status = 'in_progress' "
            "AND started_at < datetime('now', ? || ' seconds')",
            (f"-{timeout_seconds}",),
        )
        self._conn.commit()

    def is_seen(self, place_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen_places WHERE place_id = ?", (place_id,)
        ).fetchone()
        return row is not None

    def mark_seen(self, place_id: str):
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_places (place_id) VALUES (?)", (place_id,)
        )
        self._conn.commit()

    def get_progress(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ).fetchall()
        result = {"pending": 0, "in_progress": 0, "done": 0, "failed": 0}
        for row in rows:
            result[row["status"]] = row["cnt"]
        result["total"] = sum(result.values())
        seen = self._conn.execute("SELECT COUNT(*) FROM seen_places").fetchone()[0]
        result["unique_places"] = seen
        return result

    def reset_failed(self):
        self._conn.execute(
            "UPDATE tasks SET status = 'pending', worker_id = NULL, error = NULL "
            "WHERE status = 'failed'"
        )
        self._conn.commit()

    def set_meta(self, key: str, value: str):
        self._conn.execute(
            "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM run_meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def close(self):
        self._conn.close()
