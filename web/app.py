"""FastAPI web server for PlexMind Concierge."""
from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from ai.concierge import Concierge
from auth.plex_oauth import (
    request_pin, build_auth_url, poll_pin, get_user_info,
    fetch_user_watch_overlay, add_to_watchlist, remove_from_watchlist,
)
from cache.store import LibraryCache
from config import Config

logger = logging.getLogger(__name__)

# One global concierge instance — holds shared library cache
concierge = Concierge()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise library on startup."""
    try:
        count = await concierge.ensure_library()
        logger.info("PlexMind ready — %d items in library", count)
    except Exception as exc:
        logger.warning("Library init failed (%s) — will retry on first request.", exc)
    yield


app = FastAPI(title="PlexMind Concierge", lifespan=lifespan)

# Session middleware — uses a signed cookie, no server-side storage needed
_session_secret = Config.SESSION_SECRET or secrets.token_hex(32)
app.add_middleware(SessionMiddleware, secret_key=_session_secret, max_age=86400 * 30)

import pathlib
_BASE = pathlib.Path(__file__).parent
_STATIC = _BASE / "static"
_STATIC.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
templates = Jinja2Templates(directory=str(_BASE / "templates"))


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _session_user(request: Request) -> dict | None:
    """Return current signed-in user dict from session, or None."""
    token = request.session.get("user_token")
    if not token:
        return None
    return {
        "token":    token,
        "id":       request.session.get("user_id"),
        "username": request.session.get("username"),
        "thumb":    request.session.get("user_thumb"),
        "email":    request.session.get("user_email"),
    }


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = concierge.library_stats() if concierge.item_count else {}
    user  = _session_user(request)
    return templates.TemplateResponse(
        "index.html", {"request": request, "stats": stats, "user": user}
    )


# ------------------------------------------------------------------
# Chat
# ------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """Server-Sent Events streaming chat endpoint (personalised if signed in)."""
    if not concierge.item_count:
        try:
            await concierge.ensure_library()
        except Exception as exc:
            async def err_gen():
                yield f"data: ⚠️  Could not load library: {exc}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(err_gen(), media_type="text/event-stream")

    # Per-user watch overlay — personalises recommendations for signed-in users
    watch_overlay = request.session.get("watch_overlay") or None

    async def generate():
        try:
            async for chunk in concierge.ask(
                req.message, stream=True, watch_overlay=watch_overlay
            ):
                escaped = chunk.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"
        except Exception as exc:
            logger.error("Chat error: %s", exc)
            yield f"data: ⚠️  Error: {exc}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/chat/reset")
async def chat_reset():
    concierge.reset_conversation()
    return {"status": "ok"}


# ------------------------------------------------------------------
# Library
# ------------------------------------------------------------------

@app.get("/library/stats")
async def library_stats():
    return JSONResponse(concierge.library_stats())


@app.post("/library/sync")
async def library_sync():
    try:
        count = await concierge.ensure_library(force_refresh=True)
        return {"status": "ok", "items": count}
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)


@app.get("/library/titles")
async def library_titles():
    """Compact title→metadata map used by the frontend for card post-processing."""
    cache = LibraryCache()
    return JSONResponse(cache.get_title_map())


@app.get("/health")
async def health():
    return {"status": "ok", "items": concierge.item_count}


# ------------------------------------------------------------------
# Plex artwork proxy + server info
# ------------------------------------------------------------------

@app.get("/plex/server")
async def plex_server_info():
    """Return Plex machine identifier + local web URL for deep-links."""
    try:
        from plex.client import PlexClient
        client = PlexClient()
        return {
            "machine_id":  client.machine_identifier,
            "server_name": client.server_name,
            # Local URL — always works when Plex is on the same network
            "plex_web_url": f"{Config.PLEX_URL}/web",
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


@app.get("/plex/artwork/{rating_key}")
async def plex_artwork(rating_key: int, w: int = 300, h: int = 450):
    """Proxy artwork from Plex — auth token never leaves the server."""
    if not Config.PLEX_TOKEN:
        return Response(status_code=404)
    url = (
        f"{Config.PLEX_URL}/photo/:/transcode"
        f"?url=/library/metadata/{rating_key}/thumb"
        f"&width={w}&height={h}&minSize=1"
        f"&X-Plex-Token={Config.PLEX_TOKEN}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return Response(
                    content=resp.content,
                    media_type=resp.headers.get("content-type", "image/jpeg"),
                    headers={"Cache-Control": "public, max-age=3600"},
                )
    except Exception as exc:
        logger.debug("Artwork fetch failed for %d: %s", rating_key, exc)
    return Response(status_code=404)


# ------------------------------------------------------------------
# Plex OAuth (PIN-based sign-in)
# ------------------------------------------------------------------

@app.post("/auth/login")
async def auth_login(request: Request):
    """
    Step 1 — request a PIN and return the plex.tv auth URL.
    The frontend opens this URL in a popup and polls /auth/poll/{pin_id}.
    """
    try:
        pin = await request_pin()
        forward = str(request.base_url).rstrip("/") + "/auth/done"
        return {
            "pin_id":   pin["id"],
            "auth_url": build_auth_url(pin["code"], forward),
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


@app.get("/auth/poll/{pin_id}")
async def auth_poll(pin_id: int, request: Request):
    """
    Step 2 — poll until Plex sets authToken on the PIN.
    On success, store user info + fetch their personal watch overlay.
    """
    try:
        pin = await poll_pin(pin_id)
        auth_token = pin.get("authToken") or ""
        if not auth_token:
            return {"status": "pending"}

        # Fetch user profile
        user = await get_user_info(auth_token)
        request.session["user_token"]  = auth_token
        request.session["user_id"]     = user.get("id")
        request.session["username"]    = user.get("username") or user.get("title", "")
        request.session["user_thumb"]  = user.get("thumb", "")
        request.session["user_email"]  = user.get("email", "")

        # Build per-user watch overlay in the background
        # (don't block the poll response — overlay arrives on next chat request)
        asyncio.create_task(
            _refresh_watch_overlay(request, auth_token)
        )

        return {
            "status":   "ok",
            "username": request.session["username"],
            "thumb":    request.session["user_thumb"],
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


async def _refresh_watch_overlay(request: Request, user_token: str) -> None:
    """Fetch the user's personal watch history and store it in the session."""
    try:
        overlay = await fetch_user_watch_overlay(Config.PLEX_URL, user_token)
        request.session["watch_overlay"] = overlay
        logger.info("Watch overlay loaded: %d items", len(overlay))
    except Exception as exc:
        logger.warning("Watch overlay failed: %s", exc)


@app.get("/auth/me")
async def auth_me(request: Request):
    """Return the current session user, or 401."""
    user = _session_user(request)
    if not user:
        return JSONResponse({"error": "Not signed in"}, status_code=401)
    has_overlay = bool(request.session.get("watch_overlay"))
    return {**user, "watch_overlay_loaded": has_overlay}


@app.post("/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@app.get("/auth/done", response_class=HTMLResponse)
async def auth_done():
    """Landing page that Plex redirects to after the user approves the PIN."""
    return HTMLResponse("""
    <html><body style="background:#0f0f13;color:#e8e8f0;font-family:sans-serif;
                        display:flex;align-items:center;justify-content:center;height:100vh;">
      <div style="text-align:center">
        <div style="font-size:3rem">✓</div>
        <h2>Signed in! You can close this window.</h2>
      </div>
      <script>window.close();</script>
    </body></html>
    """)


# ------------------------------------------------------------------
# Watchlist
# ------------------------------------------------------------------

@app.post("/plex/watchlist/{rating_key}")
async def watchlist_add(rating_key: int, request: Request):
    """Add an item to the signed-in user's Plex watchlist."""
    user = _session_user(request)
    if not user:
        return JSONResponse({"error": "Not signed in"}, status_code=401)
    try:
        await add_to_watchlist(Config.PLEX_URL, Config.PLEX_TOKEN, user["token"], rating_key)
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Watchlist add failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.delete("/plex/watchlist/{rating_key}")
async def watchlist_remove(rating_key: int, request: Request):
    """Remove an item from the signed-in user's Plex watchlist."""
    user = _session_user(request)
    if not user:
        return JSONResponse({"error": "Not signed in"}, status_code=401)
    try:
        await remove_from_watchlist(Config.PLEX_URL, Config.PLEX_TOKEN, user["token"], rating_key)
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Watchlist remove failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)
