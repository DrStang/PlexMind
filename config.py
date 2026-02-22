import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Plex
    PLEX_URL: str = os.getenv("PLEX_URL", "http://localhost:32400")
    PLEX_TOKEN: str = os.getenv("PLEX_TOKEN", "")

    # LLM
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "ollama")  # "ollama" or "claude"
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # Cache
    CACHE_DB_PATH: str = os.getenv("CACHE_DB_PATH", "./plexmind_cache.db")
    CACHE_TTL_HOURS: int = int(os.getenv("CACHE_TTL_HOURS", "24"))

    # Web
    WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
    WEB_PORT: int = int(os.getenv("WEB_PORT", "7432"))
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
