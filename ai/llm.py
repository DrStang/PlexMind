"""LLM abstraction — supports Ollama (local) and Anthropic Claude."""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from config import Config

logger = logging.getLogger(__name__)

Message = dict  # {"role": "user"|"assistant", "content": str}


class LLMClient:
    """Unified async streaming LLM client."""

    def __init__(self):
        self.backend = Config.LLM_BACKEND

    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        stream: bool = True,
    ) -> AsyncIterator[str]:
        if self.backend == "claude":
            async for chunk in self._claude(messages, system, stream):
                yield chunk
        else:
            async for chunk in self._ollama(messages, system, stream):
                yield chunk

    async def chat_complete(
        self,
        messages: list[Message],
        system: str = "",
    ) -> str:
        """Non-streaming convenience wrapper — returns full response."""
        parts = []
        async for chunk in self.chat(messages, system, stream=False):
            parts.append(chunk)
        return "".join(parts)

    # ------------------------------------------------------------------
    # Ollama backend
    # ------------------------------------------------------------------

    async def _ollama(
        self, messages: list[Message], system: str, stream: bool
    ) -> AsyncIterator[str]:
        payload = {
            "model": Config.OLLAMA_MODEL,
            "messages": self._prepend_system(messages, system),
            "stream": stream,
        }
        url = f"{Config.OLLAMA_URL}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                if stream:
                    async with client.stream("POST", url, json=payload) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue
                else:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    yield data.get("message", {}).get("content", "")
        except httpx.ConnectError:
            yield (
                "⚠️  Cannot connect to Ollama. "
                "Make sure Ollama is running (`ollama serve`) and "
                f"OLLAMA_URL={Config.OLLAMA_URL} is correct."
            )
        except Exception as exc:
            logger.error("Ollama error: %s", exc)
            yield f"⚠️  Ollama error: {exc}"

    # ------------------------------------------------------------------
    # Anthropic Claude backend
    # ------------------------------------------------------------------

    async def _claude(
        self, messages: list[Message], system: str, stream: bool
    ) -> AsyncIterator[str]:
        if not Config.ANTHROPIC_API_KEY:
            yield "⚠️  ANTHROPIC_API_KEY is not set. Check your .env file."
            return
        try:
            import anthropic

            aclient = anthropic.AsyncAnthropic(api_key=Config.ANTHROPIC_API_KEY)
            kwargs = dict(
                model=Config.CLAUDE_MODEL,
                max_tokens=4096,
                messages=messages,
            )
            if system:
                kwargs["system"] = system

            if stream:
                async with aclient.messages.stream(**kwargs) as stream_mgr:
                    async for text in stream_mgr.text_stream:
                        yield text
            else:
                response = await aclient.messages.create(**kwargs)
                yield response.content[0].text
        except Exception as exc:
            logger.error("Claude error: %s", exc)
            yield f"⚠️  Claude error: {exc}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepend_system(messages: list[Message], system: str) -> list[Message]:
        if not system:
            return messages
        return [{"role": "system", "content": system}] + messages
