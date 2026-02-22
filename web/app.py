"""FastAPI web server for PlexMind Concierge."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ai.concierge import Concierge
from cache.store import LibraryCache
from config import Config

logger = logging.getLogger(__name__)

# One global concierge instance shared across requests
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

import pathlib
_BASE = pathlib.Path(__file__).parent
_STATIC = _BASE / "static"
_STATIC.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
templates = Jinja2Templates(directory=str(_BASE / "templates"))


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = concierge.library_stats() if concierge.item_count else {}
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})


class ChatRequest(BaseModel):
    message: str


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events streaming chat endpoint."""

    if not concierge.item_count:
        try:
            await concierge.ensure_library()
        except Exception as exc:
            async def err_gen():
                yield f"data: ⚠️  Could not load library: {exc}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(err_gen(), media_type="text/event-stream")

    async def generate():
        try:
            async for chunk in concierge.ask(req.message, stream=True):
                # Escape newlines for SSE
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


@app.get("/health")
async def health():
    return {"status": "ok", "items": concierge.item_count}


# ------------------------------------------------------------------
# Plex deep-link integration
# ------------------------------------------------------------------

@app.get("/plex/server")
async def plex_server_info():
    """Return the Plex machine identifier so the frontend can build deep-links."""
    try:
        from plex.client import PlexClient
        client = PlexClient()
        return {
            "machine_id": client.machine_identifier,
            "server_name": client.server_name,
            "plex_url": Config.PLEX_URL,
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


@app.get("/plex/artwork/{rating_key}")
async def plex_artwork(rating_key: int, w: int = 300, h: int = 450):
    """
    Proxy artwork from Plex so the browser never needs the raw token.
    Caches the image in-memory for 1 hour (via Cache-Control).
    """
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


@app.get("/library/titles")
async def library_titles():
    """
    Return a compact title→metadata map for the frontend to use when
    post-processing AI responses and rendering 'Open in Plex' cards.
    """
    cache = LibraryCache()
    return JSONResponse(cache.get_title_map())
