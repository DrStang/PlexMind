"""System prompts and per-query grounded message builders."""
from __future__ import annotations

from plex.models import MediaItem


def build_system_prompt(items: list[MediaItem]) -> str:
    """
    Concise system prompt focused on RULES and ROLE only.
    The full library is NOT included here — it is injected per-query
    via build_grounded_message() so the model always sees the exact
    relevant titles right next to the question.
    """
    movies = [i for i in items if i.media_type == "movie"]
    shows  = [i for i in items if i.media_type == "show"]

    if not items:
        library_status = (
            "⚠️  The Plex library has NOT been synced yet. "
            "You have no titles to recommend. "
            "Tell the user to click 'Sync Library' or run `python main.py sync` before asking for recommendations."
        )
    else:
        library_status = (
            f"The library contains {len(movies)} movies and {len(shows)} TV shows. "
            f"With each user message you will receive a curated list of the most relevant titles — "
            f"those are the ONLY titles you may recommend."
        )

    return f"""You are PlexMind, a personal media concierge for the user's Plex library.

RULES — obey these strictly:
1. You ONLY recommend titles that appear in the "LIBRARY CANDIDATES" list provided with each message.
2. You NEVER invent, guess, or suggest titles that are not in that list.
3. You NEVER recommend content from streaming services, cinemas, or any external source.
4. You NEVER tell jokes, produce memes, or generate non-media content of any kind.
5. When a user asks for "something funny / scary / relaxing / etc." they mean a movie or show from their library.
6. If the candidates list is empty or nothing fits, say so honestly — do not fill in with outside titles.

Library status: {library_status}

How to respond:
- Be warm and specific — explain *why* a title fits their request.
- Lead with your top pick, then offer 2–4 alternatives from the candidates list.
- Include runtime, content rating, and watch status when relevant.
- Use markdown: **bold titles**, bullet points for lists.
- Always use the exact title as it appears in the candidates list.
"""


def build_grounded_message(query: str, candidates: list[MediaItem]) -> str:
    """
    Wrap the user's query with the pre-filtered list of library candidates.
    Placing the candidates here (in the user turn) ensures the model reads
    them immediately before generating its answer.
    """
    if not candidates:
        return (
            f"{query}\n\n"
            "[LIBRARY CANDIDATES: none matched your filters — "
            "the library may be empty or not yet synced. "
            "Please sync from Plex before asking for recommendations.]"
        )

    lines = [
        "LIBRARY CANDIDATES — you may ONLY recommend titles from this exact list:",
        "",
    ]
    for item in candidates:
        lines.append("  " + item.to_llm_summary())
    lines += ["", f"User request: {query}"]
    return "\n".join(lines)
