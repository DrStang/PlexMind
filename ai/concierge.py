"""PlexMind Concierge — orchestrates Plex sync, caching, and LLM chat."""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from cache.store import LibraryCache
from config import Config
from plex.models import MediaItem
from ai.llm import LLMClient, Message
from ai.prompts import build_system_prompt, build_grounded_message
from ai.filter import filter_library

logger = logging.getLogger(__name__)


class Concierge:
    """
    High-level interface used by both the CLI and the web server.

    Usage:
        concierge = Concierge()
        await concierge.ensure_library()
        async for chunk in concierge.ask("rainy sunday movie under 2 hours"):
            print(chunk, end="", flush=True)
    """

    def __init__(self):
        self._cache = LibraryCache()
        self._llm = LLMClient()
        self._items: list[MediaItem] = []
        # Always initialise to a valid (if library-less) prompt so the LLM
        # never operates as a generic assistant even if Plex hasn't synced yet.
        self._system_prompt: str = build_system_prompt([])
        self._history: list[Message] = []

    # ------------------------------------------------------------------
    # Library management
    # ------------------------------------------------------------------

    async def ensure_library(self, force_refresh: bool = False) -> int:
        """
        Loads library from cache; syncs from Plex if stale or forced.
        Returns the number of items in the library.
        The system prompt is always updated, even if the sync fails, so the
        LLM never falls back to behaving as a generic assistant.
        """
        try:
            if force_refresh or self._cache.is_stale():
                await self._sync_from_plex()
            else:
                self._items = self._cache.get_all_items()
                logger.info("Loaded %d items from cache", len(self._items))
        finally:
            # Rebuild prompt with whatever items we have (possibly []).
            # This guarantees _system_prompt is never the empty string.
            self._system_prompt = build_system_prompt(self._items)

        return len(self._items)

    async def _sync_from_plex(self) -> None:
        """Pull fresh data from Plex and persist to cache."""
        # Import here so the app still starts without plexapi if using cache only
        from plex.client import PlexClient

        logger.info("Syncing library from Plex...")
        client = PlexClient()
        self._items = client.fetch_all_items()
        self._cache.save_items(self._items)

    def library_stats(self) -> dict:
        movies = [i for i in self._items if i.media_type == "movie"]
        shows = [i for i in self._items if i.media_type == "show"]
        last_sync = self._cache.get_last_sync()
        return {
            "total": len(self._items),
            "movies": len(movies),
            "shows": len(shows),
            "movies_watched": sum(1 for m in movies if m.watched),
            "movies_unwatched": sum(1 for m in movies if not m.watched),
            "shows_watched": sum(1 for s in shows if s.watched),
            "last_sync": last_sync.isoformat() if last_sync else None,
        }

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    async def ask(
        self,
        user_message: str,
        stream: bool = True,
        watch_overlay: dict[int, dict] | None = None,
    ) -> AsyncIterator[str]:
        """
        Send a message and yield streamed response chunks.

        watch_overlay — per-user {rating_key: {watched, watch_count}} dict
        fetched at login from the user's own Plex token.  When supplied it
        replaces the shared library's watched status so recommendations are
        personalised to that user.
        """
        candidates = filter_library(self._items, user_message, watch_overlay=watch_overlay)
        grounded = build_grounded_message(user_message, candidates)

        logger.debug(
            "Query '%s...' → %d candidates from %d items",
            user_message[:60], len(candidates), len(self._items),
        )

        # Store the original (human-readable) message in history so follow-up
        # turns read naturally, but send the grounded version to the LLM.
        self._history.append({"role": "user", "content": grounded})

        full_response = []
        async for chunk in self._llm.chat(
            messages=self._history,
            system=self._system_prompt,
            stream=stream,
        ):
            full_response.append(chunk)
            yield chunk

        assistant_text = "".join(full_response)
        self._history.append({"role": "assistant", "content": assistant_text})

    async def ask_complete(self, user_message: str) -> str:
        """Non-streaming variant — returns the full response string."""
        parts = []
        async for chunk in self.ask(user_message, stream=False):
            parts.append(chunk)
        return "".join(parts)

    def reset_conversation(self) -> None:
        """Clear chat history while keeping the library loaded."""
        self._history = []

    @property
    def history(self) -> list[Message]:
        return list(self._history)

    @property
    def item_count(self) -> int:
        return len(self._items)
