"""SQLite-backed cache for Plex library metadata."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import Config
from plex.models import MediaItem

logger = logging.getLogger(__name__)

_CREATE_ITEMS = """
CREATE TABLE IF NOT EXISTS media_items (
    key          TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    media_type   TEXT NOT NULL,
    year         INTEGER,
    duration_min INTEGER,
    rating       REAL,
    content_rating TEXT,
    genres       TEXT,   -- JSON array
    directors    TEXT,   -- JSON array
    actors       TEXT,   -- JSON array
    summary      TEXT,
    studio       TEXT,
    tagline      TEXT,
    thumb_url    TEXT,
    watched      INTEGER DEFAULT 0,
    watch_count  INTEGER DEFAULT 0,
    last_watched TEXT,
    added_at     TEXT,
    library_section TEXT,
    seasons      INTEGER,
    episodes     INTEGER,
    cached_at    TEXT NOT NULL,
    rating_key   INTEGER
)
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS cache_meta (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    synced_at TEXT NOT NULL
)
"""

# Applied to existing DBs that predate the column — safe to run repeatedly
_MIGRATIONS = [
    "ALTER TABLE media_items ADD COLUMN rating_key INTEGER",
]


class LibraryCache:
    def __init__(self, db_path: str = Config.CACHE_DB_PATH):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._con:
            self._con.execute(_CREATE_ITEMS)
            self._con.execute(_CREATE_META)
        # Apply any missing columns to pre-existing databases
        for stmt in _MIGRATIONS:
            try:
                with self._con:
                    self._con.execute(stmt)
            except sqlite3.OperationalError:
                pass  # Column already exists

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_items(self, items: list[MediaItem]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = [self._item_to_row(i, now) for i in items]
        with self._con:
            self._con.executemany(
                """INSERT OR REPLACE INTO media_items VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            self._con.execute(
                "INSERT OR REPLACE INTO cache_meta(id, synced_at) VALUES (1, ?)", (now,)
            )
        logger.info("Saved %d items to cache at %s", len(items), self._path)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all_items(self) -> list[MediaItem]:
        cur = self._con.execute("SELECT * FROM media_items")
        return [self._row_to_item(r) for r in cur.fetchall()]

    def get_last_sync(self) -> Optional[datetime]:
        row = self._con.execute("SELECT synced_at FROM cache_meta WHERE id=1").fetchone()
        if row:
            return datetime.fromisoformat(row["synced_at"])
        return None

    def is_stale(self, ttl_hours: int = Config.CACHE_TTL_HOURS) -> bool:
        last = self.get_last_sync()
        if last is None:
            return True
        age = datetime.now(timezone.utc) - last
        return age > timedelta(hours=ttl_hours)

    def get_title_map(self) -> dict:
        """Return {title_lower: {rating_key, thumb_url, title, year, media_type, watched}} for all items."""
        cur = self._con.execute(
            "SELECT title, year, media_type, watched, thumb_url, rating_key FROM media_items"
        )
        result = {}
        for row in cur.fetchall():
            result[row["title"].lower()] = {
                "title": row["title"],
                "year": row["year"],
                "media_type": row["media_type"],
                "watched": bool(row["watched"]),
                "thumb_url": row["thumb_url"],
                "rating_key": row["rating_key"] if "rating_key" in row.keys() else None,
            }
        return result

    def item_count(self) -> int:
        row = self._con.execute("SELECT COUNT(*) as n FROM media_items").fetchone()
        return row["n"] if row else 0

    def clear(self) -> None:
        with self._con:
            self._con.execute("DELETE FROM media_items")
            self._con.execute("DELETE FROM cache_meta")
        logger.info("Cache cleared")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _item_to_row(item: MediaItem, now: str) -> tuple:
        return (
            item.key,
            item.title,
            item.media_type,
            item.year,
            item.duration_minutes,
            item.rating,
            item.content_rating,
            json.dumps(item.genres),
            json.dumps(item.directors),
            json.dumps(item.actors),
            item.summary,
            item.studio,
            item.tagline,
            item.thumb_url,
            int(item.watched),
            item.watch_count,
            item.last_watched,
            item.added_at,
            item.library_section,
            item.seasons,
            item.episodes,
            now,
            item.rating_key,
        )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MediaItem:
        def _loads(val):
            return json.loads(val) if val else []

        return MediaItem(
            key=row["key"],
            title=row["title"],
            media_type=row["media_type"],
            year=row["year"],
            duration_minutes=row["duration_min"],
            rating=row["rating"],
            content_rating=row["content_rating"],
            genres=_loads(row["genres"]),
            directors=_loads(row["directors"]),
            actors=_loads(row["actors"]),
            summary=row["summary"],
            studio=row["studio"],
            tagline=row["tagline"],
            thumb_url=row["thumb_url"],
            watched=bool(row["watched"]),
            watch_count=row["watch_count"] or 0,
            last_watched=row["last_watched"],
            added_at=row["added_at"],
            library_section=row["library_section"],
            seasons=row["seasons"],
            episodes=row["episodes"],
            rating_key=row["rating_key"] if "rating_key" in row.keys() else None,
        )
