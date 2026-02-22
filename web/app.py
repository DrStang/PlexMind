"""FastAPI web server for PlexMind Concierge."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ai.concierge import Concierge
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
