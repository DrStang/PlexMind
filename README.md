# PlexMind Concierge 🎬

> *"What's a good rainy Sunday movie under 2 hours that I haven't seen?"*

A local AI concierge that knows your **entire Plex library** — including what you've watched, genres, ratings, directors, and more. Ask it anything in plain English and get smart, personalised recommendations powered by your own LLM.

---

## Features

- **Natural language queries** — mood, occasion, duration, genre, decade, cast, director
- **Watch-status awareness** — "haven't seen", "rewatch", "started but not finished"
- **Similarity search** — *"show me everything like Oppenheimer"*
- **Marathon planning** — director retrospectives, themed nights, double features
- **Streaming chat UI** — beautiful dark-mode web interface
- **Rich terminal CLI** — interactive or one-shot mode
- **Dual LLM backends** — Ollama (local, private) or Anthropic Claude
- **SQLite cache** — syncs once, instant queries forever (TTL-refreshed)
- **TV + Movies** — handles both sections from all your Plex libraries

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your Plex URL, token, and LLM settings
```

**Get your Plex token:** Settings → Account → Privacy → Plex Web → Developer Tools → Network tab → look for `X-Plex-Token` in any request. Or visit [this guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

### 3. Run

**Web UI (recommended):**
```bash
python main.py serve
# Open http://localhost:7432
```

**Interactive CLI:**
```bash
python main.py chat
```

**One-shot query:**
```bash
python main.py ask "What's a great sci-fi film under 2 hours I haven't seen?"
```

**Sync library manually:**
```bash
python main.py sync
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PLEX_URL` | `http://localhost:32400` | Your Plex Media Server URL |
| `PLEX_TOKEN` | *(required)* | Your Plex authentication token |
| `LLM_BACKEND` | `ollama` | `ollama` or `claude` |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Model to use with Ollama |
| `ANTHROPIC_API_KEY` | — | Required if using `claude` backend |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model ID |
| `CACHE_TTL_HOURS` | `24` | How often to re-sync from Plex |
| `WEB_PORT` | `7432` | Web server port |

---

## Example Queries

```
What's a rainy Sunday movie under 2 hours I haven't seen?
Show me everything like Oppenheimer in my library.
Plan me a Coen Brothers marathon.
Best unwatched thriller from the last 10 years?
I want something funny but not stupid.
What are the highest-rated movies I haven't watched yet?
Something I can watch with my parents — nothing too violent.
Recommend a show I can binge in a weekend.
What's similar to The Bear?
Compare Dune and Blade Runner 2049 for me.
```

---

## Architecture

```
PlexMind/
├── main.py           # Entry point
├── cli.py            # Rich terminal interface (chat / ask / serve / sync)
├── config.py         # Environment-based configuration
├── plex/
│   ├── client.py     # Plex API → MediaItem (plexapi)
│   └── models.py     # MediaItem dataclass
├── cache/
│   └── store.py      # SQLite cache with TTL
├── ai/
│   ├── llm.py        # Ollama + Claude streaming client
│   ├── prompts.py    # System prompt + library context builder
│   └── concierge.py  # Orchestrator (sync → cache → LLM chat)
└── web/
    ├── app.py        # FastAPI + SSE streaming
    └── templates/
        └── index.html  # Dark-mode chat UI
```

---

## LLM Backend Notes

### Ollama (local, default)
```bash
# Install: https://ollama.ai
ollama pull llama3.2   # or mistral, qwen2.5, etc.
ollama serve
```
Set `LLM_BACKEND=ollama` in `.env`.

### Anthropic Claude
Set `LLM_BACKEND=claude` and `ANTHROPIC_API_KEY=sk-ant-...` in `.env`.
Uses `claude-sonnet-4-6` by default — change with `CLAUDE_MODEL`.

---

## CLI Commands

```
python main.py --help

Commands:
  chat    Interactive multi-turn chat session
  ask     Single question, then exit
  sync    Force re-sync Plex library to cache
  serve   Start the web server

Options (all commands):
  --refresh / -r    Force re-sync from Plex before answering
```

### In-chat slash commands
| Command | Action |
|---|---|
| `/reset` | Clear conversation history |
| `/sync` | Re-sync library from Plex |
| `/stats` | Show library statistics |
| `/quit` | Exit |
