#!/usr/bin/env python3
"""PlexMind Concierge — interactive CLI powered by Rich."""
from __future__ import annotations

import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text
from rich import print as rprint

from ai.concierge import Concierge
from config import Config

app = typer.Typer(help="PlexMind Concierge — AI-powered Plex library assistant")
console = Console()

logging.basicConfig(level=logging.WARNING)


# ── Async helpers ─────────────────────────────────────────────────────

async def _boot(force_refresh: bool) -> Concierge:
    concierge = Concierge()
    with console.status("[bold yellow]Connecting to Plex and loading library…", spinner="dots"):
        count = await concierge.ensure_library(force_refresh=force_refresh)
    stats = concierge.library_stats()
    console.print(
        Panel(
            f"[bold green]✓ Library ready[/] — "
            f"[cyan]{stats['movies']}[/] movies, "
            f"[cyan]{stats['shows']}[/] shows\n"
            f"[dim]Watched: {stats['movies_watched']} movies / "
            f"{stats['shows_watched']} shows | "
            f"Unwatched movies: {stats['movies_unwatched']}[/]",
            title="[bold yellow]PlexMind Concierge[/]",
            border_style="yellow",
        )
    )
    return concierge


async def _ask_and_print(concierge: Concierge, question: str) -> None:
    """Stream a response and render it as markdown."""
    console.print()
    buffer = ""
    with Live(console=console, refresh_per_second=15) as live:
        async for chunk in concierge.ask(question, stream=True):
            buffer += chunk
            live.update(Markdown(buffer))
    console.print()


# ── Commands ──────────────────────────────────────────────────────────

@app.command()
def chat(
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Force re-sync from Plex"),
):
    """Start an interactive chat session with your library concierge."""

    async def _run():
        concierge = await _boot(refresh)
        console.print("[dim]Type your question, or [bold]/reset[/] to clear history, [bold]/quit[/] to exit.[/]\n")

        while True:
            try:
                user_input = Prompt.ask("[bold cyan]You[/]").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                console.print("[dim]Goodbye![/]")
                break
            if user_input.lower() == "/reset":
                concierge.reset_conversation()
                console.print("[green]✓ Conversation reset.[/]\n")
                continue
            if user_input.lower() == "/stats":
                stats = concierge.library_stats()
                rprint(stats)
                continue
            if user_input.lower() == "/sync":
                with console.status("Syncing from Plex…", spinner="dots"):
                    await concierge.ensure_library(force_refresh=True)
                console.print("[green]✓ Library synced.[/]\n")
                continue

            await _ask_and_print(concierge, user_input)

    asyncio.run(_run())


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your one-shot question"),
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Force re-sync from Plex"),
):
    """Ask a single question and exit (great for scripts)."""

    async def _run():
        concierge = await _boot(refresh)
        await _ask_and_print(concierge, question)

    asyncio.run(_run())


@app.command()
def sync():
    """Sync the local cache with your Plex library."""

    async def _run():
        concierge = Concierge()
        with console.status("Syncing from Plex…", spinner="dots"):
            count = await concierge.ensure_library(force_refresh=True)
        console.print(f"[green]✓ Synced {count} items.[/]")

    asyncio.run(_run())


@app.command()
def serve(
    host: str = typer.Option(Config.WEB_HOST, help="Bind host"),
    port: int = typer.Option(Config.WEB_PORT, help="Port"),
):
    """Start the PlexMind web server."""
    import uvicorn
    console.print(
        Panel(
            f"[bold green]Starting PlexMind web server[/]\n"
            f"Open [link=http://localhost:{port}]http://localhost:{port}[/link] in your browser",
            title="[bold yellow]PlexMind[/]",
            border_style="yellow",
        )
    )
    uvicorn.run("web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
