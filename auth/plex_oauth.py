"""Plex OAuth (PIN-based) helpers and watchlist API."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

PLEX_PRODUCT = "PlexMind Concierge"
PLEX_CLIENT_ID = "plexmind-concierge-v1"

_HEADERS = {
    "X-Plex-Product": PLEX_PRODUCT,
    "X-Plex-Client-Identifier": PLEX_CLIENT_ID,
    "Accept": "application/json",
}


# ------------------------------------------------------------------
# PIN OAuth flow
# ------------------------------------------------------------------

async def request_pin() -> dict:
    """Request a fresh PIN from plex.tv. Returns {id, code, ...}."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://plex.tv/api/v2/pins",
            params={"strong": "true"},
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


def build_auth_url(pin_code: str, forward_url: str) -> str:
    """Return the plex.tv URL the user must open to approve the PIN."""
    params = urlencode({
        "clientID": PLEX_CLIENT_ID,
        "code": pin_code,
        "forwardUrl": forward_url,
        "context[device][product]": PLEX_PRODUCT,
    })
    return f"https://app.plex.tv/auth#?{params}"


async def poll_pin(pin_id: int) -> dict:
    """
    Poll for PIN status. Returns the full pin object.
    Check `data["authToken"]` — it's non-empty once the user approves.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://plex.tv/api/v2/pins/{pin_id}",
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_info(auth_token: str) -> dict:
    """Return the signed-in user's profile from plex.tv."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://plex.tv/api/v2/user",
            headers={**_HEADERS, "X-Plex-Token": auth_token},
        )
        resp.raise_for_status()
        return resp.json()


# ------------------------------------------------------------------
# Per-user watch history (fetched using the user's own token)
# ------------------------------------------------------------------

async def fetch_user_watch_overlay(
    plex_url: str,
    user_token: str,
) -> dict[int, dict]:
    """
    Connect to the local Plex server with the user's own token and pull
    their personal watch history.  Returns {rating_key: {watched, watch_count}}.
    This is run once after login and cached in the session.
    """
    overlay: dict[int, dict] = {}
    try:
        from plexapi.server import PlexServer
        server = PlexServer(plex_url, user_token)
        for section in server.library.sections():
            if section.type not in ("movie", "show"):
                continue
            for item in section.all():
                rk = getattr(item, "ratingKey", None)
                if rk:
                    overlay[int(rk)] = {
                        "watched": bool(getattr(item, "viewCount", 0)),
                        "watch_count": getattr(item, "viewCount", 0) or 0,
                    }
    except Exception as exc:
        logger.warning("Could not fetch per-user watch data: %s", exc)
    return overlay


# ------------------------------------------------------------------
# Watchlist (Plex.tv cloud, requires user token)
# ------------------------------------------------------------------

async def add_to_watchlist(plex_url: str, server_token: str, user_token: str, rating_key: int) -> None:
    """Add an item to the signed-in user's Plex watchlist."""
    from plexapi.server import PlexServer
    from plexapi.myplex import MyPlexAccount
    server = PlexServer(plex_url, server_token)
    item = server.fetchItem(rating_key)
    account = MyPlexAccount(token=user_token)
    account.addToWatchlist(item)


async def remove_from_watchlist(plex_url: str, server_token: str, user_token: str, rating_key: int) -> None:
    """Remove an item from the signed-in user's Plex watchlist."""
    from plexapi.server import PlexServer
    from plexapi.myplex import MyPlexAccount
    server = PlexServer(plex_url, server_token)
    item = server.fetchItem(rating_key)
    account = MyPlexAccount(token=user_token)
    account.removeFromWatchlist(item)
