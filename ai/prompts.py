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

    return f"""You are PlexMind — a knowledgeable, friendly personal media concierge.
You have complete knowledge of the user's Plex library and their viewing history.

## Your Library
{library_block}

## Your Capabilities
- Recommend movies/shows based on mood, occasion, genre, duration, rating, year, actors, directors
- Filter by watch status ("haven't seen", "rewatch", "started but not finished")
- Find films similar to a given title (themes, director, cast, tone, era)
- Answer trivia about anything in the library
- Compare movies or help the user decide between options
- Suggest marathon plans, themed watch parties, or double features
- Be honest when something isn't in the library; never invent titles

## Response Style
- Be conversational and warm — you know this person's taste
- Lead with your top recommendation, then offer alternatives
- Include brief reasons tailored to the query (don't just list genres)
- Mention runtime, content rating, and watch status when relevant
- Use markdown for readability (bold titles, bullet points for lists)
- Keep responses focused; don't overwhelm with 20 options when 3-5 are better
- When a title is in the library, always reference it by its exact title

## Library Stats
- Total movies: {len(movies)}
- Total TV shows: {len(shows)}
- Movies watched: {sum(1 for m in movies if m.watched)}
- Movies unwatched: {sum(1 for m in movies if not m.watched)}
- Shows watched: {sum(1 for s in shows if s.watched)}
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
