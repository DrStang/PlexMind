"""Query-time library relevance filter.

Scores every item in the library against the user's query and returns
the top-N most relevant results.  This lets us inject a tight, focused
list into the LLM's context instead of dumping the whole library and
hoping the model stays grounded.
"""
from __future__ import annotations

import re
from plex.models import MediaItem

# Mood / vibe words → genres they map to
_MOOD_GENRE: dict[str, list[str]] = {
    "funny":        ["Comedy"],
    "comedy":       ["Comedy"],
    "laugh":        ["Comedy"],
    "humor":        ["Comedy"],
    "humour":       ["Comedy"],
    "hilarious":    ["Comedy"],
    "lighthearted": ["Comedy", "Family"],
    "scary":        ["Horror", "Thriller"],
    "horror":       ["Horror"],
    "terrifying":   ["Horror"],
    "thriller":     ["Thriller"],
    "suspense":     ["Thriller", "Mystery"],
    "suspenseful":  ["Thriller", "Mystery"],
    "mystery":      ["Mystery"],
    "romantic":     ["Romance"],
    "romance":      ["Romance"],
    "love story":   ["Romance"],
    "action":       ["Action"],
    "adventure":    ["Adventure"],
    "epic":         ["Action", "Adventure", "Drama"],
    "sci-fi":       ["Science Fiction", "Sci-Fi"],
    "scifi":        ["Science Fiction", "Sci-Fi"],
    "science fiction": ["Science Fiction"],
    "space":        ["Science Fiction", "Sci-Fi"],
    "fantasy":      ["Fantasy"],
    "superhero":    ["Action", "Science Fiction"],
    "drama":        ["Drama"],
    "documentary":  ["Documentary"],
    "doc":          ["Documentary"],
    "animation":    ["Animation"],
    "animated":     ["Animation"],
    "anime":        ["Animation", "Anime"],
    "western":      ["Western"],
    "war":          ["War", "History"],
    "historical":   ["History", "Drama"],
    "crime":        ["Crime"],
    "heist":        ["Crime", "Thriller"],
    "family":       ["Family"],
    "kids":         ["Family", "Animation"],
    "musical":      ["Music"],
    "music":        ["Music"],
    "sport":        ["Sport"],
    "sports":       ["Sport"],
    "biopic":       ["Biography", "Drama", "History"],
    "biography":    ["Biography"],
    "mind-bending": ["Science Fiction", "Mystery", "Thriller"],
    "mindbending":  ["Science Fiction", "Mystery", "Thriller"],
    "mind bending": ["Science Fiction", "Mystery", "Thriller"],
    "intelligent":  ["Drama", "Mystery", "Thriller"],
    "smart":        ["Drama", "Mystery", "Thriller"],
    "feel-good":    ["Comedy", "Family", "Romance"],
    "feel good":    ["Comedy", "Family", "Romance"],
    "dark":         ["Crime", "Thriller", "Drama", "Horror"],
    "gritty":       ["Crime", "Drama", "Thriller"],
    "violent":      ["Action", "Crime", "Thriller"],
    "intense":      ["Thriller", "Drama", "Action"],
    "slow burn":    ["Drama", "Thriller"],
    "slow-burn":    ["Drama", "Thriller"],
    "rainy":        ["Drama", "Mystery", "Thriller"],
    "cozy":         ["Comedy", "Family", "Romance"],
    "relaxing":     ["Comedy", "Family", "Documentary"],
    "chill":        ["Comedy", "Family"],
    "binge":        [],   # no genre bias — just include everything
    "marathon":     [],
}

_DURATION_RE = re.compile(
    r"under\s+(\d+)\s*(hours?|hrs?|h\b|minutes?|mins?|m\b)", re.I
)

_UNWATCHED_SIGNALS = frozenset([
    "haven't seen", "havent seen", "haven't watched", "havent watched",
    "not seen", "not watched", "unwatched", "never seen", "never watched",
    "new to me", "haven't", "first time",
])

_WATCHED_SIGNALS = frozenset([
    "rewatch", "re-watch", "watch again", "seen before", "already seen",
    "revisit",
])


def filter_library(
    items: list[MediaItem],
    query: str,
    max_results: int = 50,
    watch_overlay: dict[int, dict] | None = None,
) -> list[MediaItem]:
    """
    Score and rank items against the query.  Hard-exclude items that
    violate explicit filters (duration, watch status, media type).
    Return the top max_results by score.

    watch_overlay — optional per-user dict {rating_key: {watched, watch_count}}
    that overrides the shared library's watched state with the signed-in
    user's actual view history.
    """
    if not items:
        return []

    q = query.lower()

    def _watched(item: MediaItem) -> bool:
        """Resolve watched status: user overlay takes priority over shared cache."""
        if watch_overlay and item.rating_key:
            entry = watch_overlay.get(item.rating_key)
            if entry is not None:
                return entry["watched"]
        return item.watched

    max_minutes = _parse_duration(q)
    want_unwatched = any(sig in q for sig in _UNWATCHED_SIGNALS)
    want_watched   = any(sig in q for sig in _WATCHED_SIGNALS)
    want_movies    = any(w in q for w in ("movie", "film", "cinema", "flick"))
    want_shows     = any(w in q for w in ("show", "series", "tv ", "television", "binge", "episode"))

    # Build genre targets from mood words
    target_genres: set[str] = set()
    for mood, genres in _MOOD_GENRE.items():
        if mood in q:
            target_genres.update(g.lower() for g in genres)

    query_words = set(re.findall(r"\w+", q))

    scored: list[tuple[float, MediaItem]] = []

    for item in items:
        # ── Hard exclusions ──────────────────────────────────────────
        if want_movies and not want_shows and item.media_type != "movie":
            continue
        if want_shows and not want_movies and item.media_type != "show":
            continue
        if max_minutes and item.duration_minutes:
            if item.duration_minutes > max_minutes:
                continue
        item_watched = _watched(item)
        if want_unwatched and item_watched:
            continue
        if want_watched and not item_watched:
            continue

        # ── Scoring ──────────────────────────────────────────────────
        score: float = 0.0

        # Genre match (most important signal)
        item_genres_lc = {g.lower() for g in item.genres}
        genre_hits = len(item_genres_lc & target_genres)
        score += genre_hits * 12

        # Title words appear in query (catches "like Oppenheimer", "Nolan" etc.)
        title_words = set(re.findall(r"\w+", item.title.lower()))
        score += len(title_words & query_words) * 10

        # Person mentions (director / actor named in query)
        for person in item.directors + item.actors:
            person_lc = person.lower()
            # Full name match
            if person_lc in q:
                score += 15
            else:
                # Last-name match
                last = person_lc.split()[-1] if person_lc.split() else ""
                if last and len(last) > 3 and last in query_words:
                    score += 8

        # Prefer unwatched when user hasn't said they want rewatches
        if not want_watched and not item_watched:
            score += 4

        # Rating bonus (0–10 → adds up to 10 points)
        score += (item.rating or 0)

        scored.append((score, item))

    # Sort by score desc, break ties by rating
    scored.sort(key=lambda x: (x[0], x[1].rating or 0), reverse=True)
    return [item for _, item in scored[:max_results]]


def _parse_duration(query: str) -> int | None:
    """Return a max-duration in minutes if the query specifies one."""
    m = _DURATION_RE.search(query)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        return value * 60
    return value
