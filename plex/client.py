"""Plex Media Server client — fetches and normalises library data."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from plexapi.server import PlexServer
from plexapi.exceptions import Unauthorized, NotFound
from plexapi.video import Movie, Show

from config import Config
from plex.models import MediaItem

logger = logging.getLogger(__name__)


class PlexClient:
    def __init__(self, url: str = Config.PLEX_URL, token: str = Config.PLEX_TOKEN):
        if not token:
            raise ValueError(
                "PLEX_TOKEN is not set. "
                "Find yours at: https://www.plexopolis.com/api/token"
            )
        try:
            self._server = PlexServer(url, token)
            logger.info("Connected to Plex: %s", self._server.friendlyName)
        except Unauthorized:
            raise ValueError("Invalid Plex token — check your PLEX_TOKEN setting.")
        except Exception as exc:
            raise ConnectionError(f"Cannot reach Plex at {url}: {exc}") from exc

    @property
    def server_name(self) -> str:
        return self._server.friendlyName

    @property
    def machine_identifier(self) -> str:
        return self._server.machineIdentifier

    # ------------------------------------------------------------------
    # Library fetching
    # ------------------------------------------------------------------

    def fetch_all_items(self) -> list[MediaItem]:
        """Return every movie and TV show in all Plex libraries."""
        items: list[MediaItem] = []
        for section in self._server.library.sections():
            if section.type == "movie":
                items.extend(self._fetch_movies(section))
            elif section.type == "show":
                items.extend(self._fetch_shows(section))
        logger.info("Fetched %d total items from Plex", len(items))
        return items

    def fetch_watch_history(self) -> dict[str, dict]:
        """Return a dict keyed by item key with watch metadata."""
        history: dict[str, dict] = {}
        try:
            for entry in self._server.history():
                key = entry.grandparentKey or entry.parentKey or entry.key
                if key not in history:
                    history[key] = {
                        "watch_count": 0,
                        "last_watched": None,
                    }
                history[key]["watch_count"] += 1
                viewed = getattr(entry, "viewedAt", None)
                if viewed:
                    iso = viewed.isoformat()
                    if (
                        history[key]["last_watched"] is None
                        or iso > history[key]["last_watched"]
                    ):
                        history[key]["last_watched"] = iso
        except Exception as exc:
            logger.warning("Could not fetch watch history: %s", exc)
        return history

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_movies(self, section) -> list[MediaItem]:
        items = []
        for movie in section.all():
            try:
                items.append(self._movie_to_item(movie, section.title))
            except Exception as exc:
                logger.debug("Skipping movie %s: %s", getattr(movie, "title", "?"), exc)
        return items

    def _fetch_shows(self, section) -> list[MediaItem]:
        items = []
        for show in section.all():
            try:
                items.append(self._show_to_item(show, section.title))
            except Exception as exc:
                logger.debug("Skipping show %s: %s", getattr(show, "title", "?"), exc)
        return items

    @staticmethod
    def _safe_minutes(duration_ms: Optional[int]) -> Optional[int]:
        if duration_ms:
            return max(1, round(duration_ms / 60_000))
        return None

    @staticmethod
    def _safe_rating(obj) -> Optional[float]:
        r = getattr(obj, "audienceRating", None) or getattr(obj, "rating", None)
        if r is not None:
            return round(float(r), 1)
        return None

    @staticmethod
    def _safe_list(obj, attr: str) -> list[str]:
        items = getattr(obj, attr, []) or []
        return [getattr(i, "tag", str(i)) for i in items]

    @staticmethod
    def _safe_date(obj, attr: str) -> Optional[str]:
        val = getattr(obj, attr, None)
        if isinstance(val, datetime):
            return val.isoformat()
        return None

    def _movie_to_item(self, movie: Movie, section_title: str) -> MediaItem:
        return MediaItem(
            key=movie.key,
            title=movie.title,
            media_type="movie",
            year=getattr(movie, "year", None),
            duration_minutes=self._safe_minutes(getattr(movie, "duration", None)),
            rating=self._safe_rating(movie),
            content_rating=getattr(movie, "contentRating", None),
            genres=self._safe_list(movie, "genres"),
            directors=self._safe_list(movie, "directors"),
            actors=self._safe_list(movie, "roles"),
            summary=getattr(movie, "summary", None),
            studio=getattr(movie, "studio", None),
            tagline=getattr(movie, "tagline", None),
            thumb_url=getattr(movie, "thumbUrl", None),
            watched=bool(getattr(movie, "viewCount", 0)),
            watch_count=getattr(movie, "viewCount", 0) or 0,
            last_watched=self._safe_date(movie, "lastViewedAt"),
            added_at=self._safe_date(movie, "addedAt"),
            library_section=section_title,
            rating_key=getattr(movie, "ratingKey", None),
        )

    def _show_to_item(self, show: Show, section_title: str) -> MediaItem:
        seasons = getattr(show, "childCount", None)
        episodes = getattr(show, "leafCount", None)
        ep_dur = self._safe_minutes(getattr(show, "duration", None))
        return MediaItem(
            key=show.key,
            title=show.title,
            media_type="show",
            year=getattr(show, "year", None),
            duration_minutes=ep_dur,  # per-episode minutes
            rating=self._safe_rating(show),
            content_rating=getattr(show, "contentRating", None),
            genres=self._safe_list(show, "genres"),
            directors=[],  # shows have per-episode directors
            actors=self._safe_list(show, "roles"),
            summary=getattr(show, "summary", None),
            studio=getattr(show, "studio", None),
            tagline=getattr(show, "tagline", None),
            thumb_url=getattr(show, "thumbUrl", None),
            watched=bool(getattr(show, "viewCount", 0)),
            watch_count=getattr(show, "viewCount", 0) or 0,
            last_watched=self._safe_date(show, "lastViewedAt"),
            added_at=self._safe_date(show, "addedAt"),
            library_section=section_title,
            seasons=seasons,
            episodes=episodes,
            rating_key=getattr(show, "ratingKey", None),
        )
