from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MediaItem:
    """Unified representation of a Plex media item."""
    key: str
    title: str
    media_type: str          # "movie" | "show" | "episode"
    year: Optional[int]
    duration_minutes: Optional[int]
    rating: Optional[float]  # audience rating 0-10
    content_rating: Optional[str]  # PG, R, TV-MA, etc.
    genres: list[str] = field(default_factory=list)
    directors: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    studio: Optional[str] = None
    tagline: Optional[str] = None
    thumb_url: Optional[str] = None
    watched: bool = False
    watch_count: int = 0
    last_watched: Optional[str] = None  # ISO date string
    added_at: Optional[str] = None
    library_section: Optional[str] = None
    # TV-specific
    seasons: Optional[int] = None
    episodes: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "media_type": self.media_type,
            "year": self.year,
            "duration_minutes": self.duration_minutes,
            "rating": self.rating,
            "content_rating": self.content_rating,
            "genres": self.genres,
            "directors": self.directors,
            "actors": self.actors,
            "summary": self.summary,
            "studio": self.studio,
            "tagline": self.tagline,
            "thumb_url": self.thumb_url,
            "watched": self.watched,
            "watch_count": self.watch_count,
            "last_watched": self.last_watched,
            "added_at": self.added_at,
            "library_section": self.library_section,
            "seasons": self.seasons,
            "episodes": self.episodes,
        }

    def to_llm_summary(self) -> str:
        """Compact text representation for LLM context."""
        parts = [f'"{self.title}"']
        if self.year:
            parts.append(f"({self.year})")
        if self.media_type == "show":
            if self.seasons:
                parts.append(f"[TV, {self.seasons}s]")
        else:
            if self.duration_minutes:
                parts.append(f"[{self.duration_minutes}min]")
        if self.rating:
            parts.append(f"★{self.rating:.1f}")
        if self.content_rating:
            parts.append(self.content_rating)
        if self.genres:
            parts.append(", ".join(self.genres[:3]))
        if self.watched:
            parts.append("(watched)")
        if self.directors:
            parts.append(f"dir. {', '.join(self.directors[:2])}")
        if self.actors:
            parts.append(f"with {', '.join(self.actors[:3])}")
        return " | ".join(parts)
