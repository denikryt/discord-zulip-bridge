from __future__ import annotations

from pathlib import Path
import sqlite3
import threading


class BridgeStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        if self._path.parent != Path("."):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forum_topic_map (
                    discord_thread_id INTEGER PRIMARY KEY,
                    discord_thread_name TEXT NOT NULL,
                    zulip_topic TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.commit()

    def get_topic_for_thread(self, discord_thread_id: int) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT zulip_topic FROM forum_topic_map WHERE discord_thread_id = ?",
                (discord_thread_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["zulip_topic"])

    def get_thread_for_topic(self, zulip_topic: str) -> tuple[int, str] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT discord_thread_id, discord_thread_name FROM forum_topic_map WHERE zulip_topic = ?",
                (zulip_topic,),
            ).fetchone()
        if row is None:
            return None
        return int(row["discord_thread_id"]), str(row["discord_thread_name"])

    def store_forum_mapping(self, discord_thread_id: int, discord_thread_name: str, zulip_topic: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO forum_topic_map (
                    discord_thread_id,
                    discord_thread_name,
                    zulip_topic
                ) VALUES (?, ?, ?)
                """,
                (discord_thread_id, discord_thread_name, zulip_topic),
            )
            self._conn.commit()
