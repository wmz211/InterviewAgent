"""
AudioStreamHandler — ties together ASR → TTS per WebSocket session.

Protocol (JSON text frames + binary audio frames):
  Client → Server:
    binary                            raw PCM 16kHz 16bit mono audio chunks
    {"type": "end_speech"}            candidate finished speaking
    {"type": "tts_begin"}             open a new streaming TTS session
    {"type": "tts_append", "text"}    feed text into the open TTS session
    {"type": "tts_finish"}            finalize TTS (audio will stream back)
    {"type": "ping"}                  keepalive

  Server → Client:
    {"type": "asr_partial", "text"}   interim transcript
    {"type": "asr_final",   "text"}   confirmed transcript (fills input box)
    {"type": "tts_start"}             TTS audio stream begins
    binary                            raw PCM TTS audio chunks
    {"type": "tts_done"}              TTS audio stream ended
    {"type": "error",  "detail"}      error message
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import WebSocket
from loguru import logger

from app.audio.asr import StreamingASR
from app.audio.tts import TtsLiveSession
from app.core.session_store import get_session_store


_MIN_CHUNK = 320  # bytes


class AudioStreamHandler:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._ws: Optional[WebSocket] = None
        self._asr: Optional[StreamingASR] = None
        self._asr_lock = asyncio.Lock()
        self._store = get_session_store()
        # Accumulated ASR text across auto-restarts (DashScope closes on sentence_end)
        self._asr_accumulated: str = ""
        # Streaming TTS state — one session per LLM turn
        self._tts_session: Optional[TtsLiveSession] = None
        self._tts_drain_task: Optional[asyncio.Task] = None

    # ── WebSocket helpers ──────────────────────────────────────────────

    async def _send_json(self, data: dict) -> None:
        if self._ws:
            try:
                await self._ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                pass

    async def _send_bytes(self, data: bytes) -> None:
        if self._ws:
            try:
                await self._ws.send_bytes(data)
            except Exception:
                pass

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def attach(self, websocket: WebSocket) -> None:
        self._ws = websocket
        await self._start_asr()

    async def detach(self) -> None:
        self._ws = None
        # Stop any running TTS session
        await self._cancel_tts()
        # Stop ASR
        async with self._asr_lock:
            if self._asr:
                try:
                    await self._asr.stop()
                except Exception:
                    pass
                self._asr = None

    # ── ASR management ─────────────────────────────────────────────────

    async def _start_asr(self) -> None:
        async with self._asr_lock:
            self._asr = StreamingASR()
            await self._asr.start()
            asyncio.create_task(self._drain_asr())

    async def _drain_asr(self) -> None:
        """Forward ASR partials to client. Session stays open across sentence_end."""
        asr = self._asr
        if asr is None:
            return
        while self._ws and self._asr is asr:
            result = await asr.get_partial(timeout=0.05)
            if result is None:
                await asyncio.sleep(0.01)
                continue
            await self._send_json({"type": "asr_partial", "text": result.text})

    async def _restart_asr(self) -> None:
        async with self._asr_lock:
            if self._asr:
                old = self._asr
                self._asr = None
                try:
                    await old.stop()
                except Exception:
                    pass
            self._asr = StreamingASR()
            await self._asr.start()
            asyncio.create_task(self._drain_asr())

    # ── Audio input ────────────────────────────────────────────────────

    async def handle_audio(self, data: bytes) -> None:
        if len(data) < _MIN_CHUNK:
            return
        async with self._asr_lock:
            # Auto-restart if DashScope auto-closed the session on sentence_end
            if self._asr is None or self._asr.is_closed:
                if self._asr is not None:
                    # Save text from the now-closed session before replacing it
                    self._asr_accumulated += self._asr.final_text
                self._asr = StreamingASR()
                await self._asr.start()
                asyncio.create_task(self._drain_asr())
            await self._asr.send(data)

    async def handle_end_speech(self) -> None:
        """Stop recording, collect full ASR text, send to client to fill input box."""
        async with self._asr_lock:
            asr = self._asr
            self._asr = None  # stop accepting new audio immediately

        if asr is None:
            await self._send_json({"type": "error", "detail": "未识别到语音，请重试"})
            return

        try:
            await asr.stop()
        except Exception as e:
            logger.warning(f"ASR stop error (ignored): {e}")

        full_text = (self._asr_accumulated + asr.final_text).strip()
        self._asr_accumulated = ""  # reset for next recording

        if full_text:
            await self._send_json({"type": "asr_final", "text": full_text})
        else:
            await self._send_json({"type": "error", "detail": "未识别到语音，请重试"})
        # Do NOT restart here — handle_audio will create a fresh session on next recording

    # ── Streaming TTS ──────────────────────────────────────────────────

    async def _cancel_tts(self) -> None:
        """Cancel any running TTS drain task and clean up session."""
        if self._tts_drain_task and not self._tts_drain_task.done():
            self._tts_drain_task.cancel()
            try:
                await self._tts_drain_task
            except asyncio.CancelledError:
                pass
        self._tts_drain_task = None
        self._tts_session = None

    async def _drain_tts(self) -> None:
        """Stream audio chunks from current TTS session to client."""
        session = self._tts_session
        if session is None:
            return
        chunk_count = 0
        byte_count = 0
        await self._send_json({"type": "tts_start"})
        try:
            async for chunk in session.chunks():
                chunk_count += 1
                byte_count += len(chunk)
                await self._send_bytes(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"TTS drain error: {e}")
        finally:
            logger.debug(f"TTS drain finished: chunks={chunk_count} bytes={byte_count}")
            await self._send_json({"type": "tts_done"})
            if self._tts_session is session:
                self._tts_session = None

    async def handle_tts_begin(self) -> None:
        """Open a new streaming TTS session for this turn."""
        # Cancel any previous turn's TTS
        await self._cancel_tts()
        session = TtsLiveSession()
        await session.open()
        self._tts_session = session
        self._tts_drain_task = asyncio.create_task(self._drain_tts())

    async def handle_tts_append(self, text: str) -> None:
        """Append text to the current streaming TTS session."""
        if self._tts_session and text.strip():
            await self._tts_session.append(text)

    async def handle_tts_finish(self) -> None:
        """Finalize the current streaming TTS session."""
        if self._tts_session:
            await self._tts_session.finish()


# ── Utility ────────────────────────────────────────────────────────────────

def _extract_last_ai_text(messages: list) -> str:
    for msg in reversed(messages):
        if type(msg).__name__ == "AIMessage" and not getattr(msg, "tool_calls", None):
            content = msg.content
            if isinstance(content, list):
                return " ".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict)
                )
            return str(content)
    return ""


# ── Session-level handler registry ────────────────────────────────────

_handlers: dict[str, AudioStreamHandler] = {}


def get_or_create_handler(session_id: str) -> AudioStreamHandler:
    if session_id not in _handlers:
        _handlers[session_id] = AudioStreamHandler(session_id)
    return _handlers[session_id]


def remove_handler(session_id: str) -> None:
    _handlers.pop(session_id, None)
