"""System prompts and library context builders for the Concierge."""
from __future__ import annotations

from plex.models import MediaItem

# Maximum items to include in full detail; the rest get compact summaries
_FULL_DETAIL_LIMIT = 60
_COMPACT_LIMIT = 500


def build_system_prompt(items: list[MediaItem]) -> str:
    movies = [i for i in items if i.media_type == "movie"]
    shows = [i for i in items if i.media_type == "show"]
    library_block = _build_library_block(items)
    no_library_warning = (
        "\n⚠️  The library has not been synced yet. "
        "Tell the user to click 'Sync Library' or run `python main.py sync` "
        "so you can see their actual Plex content before making recommendations."
        if not items else ""
    )

    return f"""You are PlexMind, a personal media concierge exclusively for the user's Plex library.

CRITICAL RULES — follow these above all else:
1. You ONLY recommend movies and TV shows that appear in the library list below.
2. You NEVER tell jokes, recite memes, share viral videos, or produce any non-media content.
3. You NEVER recommend anything outside the library — no streaming services, no theatres, no made-up titles.
4. Every answer must be grounded in specific titles from the library. If nothing fits, say so honestly.
5. When the user asks for "something funny / scary / romantic / etc." they always mean a movie or TV show from their library — never a joke or general content.{no_library_warning}

## The User's Plex Library
{library_block}

## Library Stats
- Movies: {len(movies)} total ({sum(1 for m in movies if m.watched)} watched, {sum(1 for m in movies if not m.watched)} unwatched)
- TV Shows: {len(shows)} total ({sum(1 for s in shows if s.watched)} watched)

## What You Can Do
- Recommend titles by mood, occasion, genre, runtime, rating, year, cast, or director
- Filter by watch status ("haven't seen", "want to rewatch", "something new")
- Find titles similar to a given film or show (themes, tone, director, era, cast)
- Plan marathons, double features, or themed watch nights
- Compare two titles to help the user decide
- Answer questions about anything in the library

## How to Respond
- Be warm and specific — explain *why* a title fits their request
- Lead with your best pick, then offer 2–4 alternatives
- Always use the exact title as it appears in the library
- Include runtime, content rating, and watch status when relevant
- Use markdown: **bold titles**, bullet points for lists
- If nothing in the library fits, say so clearly and suggest the closest alternatives you do have
"""


def _build_library_block(items: list[MediaItem]) -> str:
    """Build a compact but rich text representation of the whole library."""
    if not items:
        return "(Library is empty or not yet synced)"

    movies = sorted(
        [i for i in items if i.media_type == "movie"],
        key=lambda x: (x.rating or 0),
        reverse=True,
    )
    shows = sorted(
        [i for i in items if i.media_type == "show"],
        key=lambda x: (x.rating or 0),
        reverse=True,
    )

    lines = ["### Movies"]
    lines.extend(_format_items(movies))
    lines.append("")
    lines.append("### TV Shows")
    lines.extend(_format_items(shows))

    return "\n".join(lines)


def _format_items(items: list[MediaItem]) -> list[str]:
    lines = []
    for item in items[:_COMPACT_LIMIT]:
        lines.append("  " + item.to_llm_summary())
    if len(items) > _COMPACT_LIMIT:
        lines.append(f"  ... and {len(items) - _COMPACT_LIMIT} more")
    return lines


def build_context_message(user_query: str) -> str:
    """Wraps the user query — could add retrieval context here in future."""
    return user_query
