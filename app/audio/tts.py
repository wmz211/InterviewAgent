"""
TTS client — qwen3-tts-flash-realtime via dashscope.audio.qwen_tts_realtime.

Two usage modes:

1. One-shot (for greetings etc.):
    async for chunk in tts_stream("你好"):
        await websocket.send_bytes(chunk)

2. Streaming per-turn (low-latency, one WS connection per turn):
    session = TtsLiveSession()
    session.open()
    session.append("第一句话。")   # call as sentences arrive
    session.append("第二句话。")
    session.finish()
    async for chunk in session.chunks():
        await websocket.send_bytes(chunk)
"""
from __future__ import annotations

import asyncio
import base64
from typing import AsyncIterator, Optional

import dashscope
from loguru import logger

from app.config import get_settings

settings = get_settings()

_AUDIO_FORMAT = None


def _get_audio_format():
    global _AUDIO_FORMAT
    if _AUDIO_FORMAT is None:
        from dashscope.audio.qwen_tts_realtime import AudioFormat
        _AUDIO_FORMAT = AudioFormat.PCM_24000HZ_MONO_16BIT
    return _AUDIO_FORMAT


def _connect_tts(callback):
    """Create and connect a QwenTtsRealtime instance. Returns the tts object.

    Wraps the user callback so we can intercept `session.created` and wait
    for it before sending `update_session`.  This avoids a race where we
    send config before the server is ready — which causes an immediate
    disconnect ("Invalid close frame").
    """
    import time
    import threading
    from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback

    dashscope.api_key = settings.dashscope_api_key
    logger.info(f"TTS connecting: model={settings.tts_model_name} voice={settings.tts_voice}")

    session_ready = threading.Event()

    class _WrapCB(QwenTtsRealtimeCallback):
        """Intercept session.created, forward everything to the real callback."""
        def on_open(self):
            callback.on_open()

        def on_close(self, code, msg):
            session_ready.set()          # unblock in case we're still waiting
            callback.on_close(code, msg)

        def on_event(self, response: dict):
            t = response.get("type", "")
            if t == "session.created":
                logger.debug(f"TTS session.created received: {str(response)[:300]}")
                session_ready.set()
            callback.on_event(response)

    tts = QwenTtsRealtime(model=settings.tts_model_name, callback=_WrapCB())
    tts.connect()

    # Wait until the server has actually created the session
    if not session_ready.wait(timeout=5):
        logger.warning("TTS: timed out waiting for session.created — sending update_session anyway")

    logger.debug("TTS sending update_session...")
    kwargs = dict(
        voice=settings.tts_voice,
        response_format=_get_audio_format(),
        mode="server_commit",
        speech_rate=settings.tts_speech_rate,
    )
    if settings.tts_instructions:
        kwargs["instructions"] = settings.tts_instructions
        kwargs["optimize_instructions"] = True
    tts.update_session(**kwargs)
    logger.debug("TTS update_session sent")
    return tts


# ── One-shot stream ─────────────────────────────────────────────────────────

async def tts_stream(text: str) -> AsyncIterator[bytes]:
    """One-shot: synthesize full text → yield PCM chunks."""
    if not text.strip():
        return

    from dashscope.audio.qwen_tts_realtime import QwenTtsRealtimeCallback

    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    class _CB(QwenTtsRealtimeCallback):
        def on_open(self): logger.debug("TTS WS opened")

        def on_close(self, code, msg):
            logger.debug(f"TTS WS closed: {code}")
            loop.call_soon_threadsafe(queue.put_nowait, None)

        def on_event(self, response: dict):
            try:
                t = response.get("type", "")
                if t not in ("response.audio.delta",):
                    logger.debug(f"TTS event: {t} — {str(response)[:200]}")
                if t == "response.audio.delta":
                    raw = response.get("delta", "")
                    if raw:
                        loop.call_soon_threadsafe(queue.put_nowait, base64.b64decode(raw))
                elif t == "session.finished":
                    loop.call_soon_threadsafe(queue.put_nowait, None)
            except Exception as e:
                logger.error(f"TTS callback error: {e}")
                loop.call_soon_threadsafe(queue.put_nowait, None)

    tts = await asyncio.get_event_loop().run_in_executor(None, _connect_tts, _CB())
    for chunk in _split_text(text):
        tts.append_text(chunk)
        await asyncio.sleep(0)
    tts.finish()

    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        yield chunk


async def tts_bytes(text: str) -> bytes:
    buf = bytearray()
    async for chunk in tts_stream(text):
        buf.extend(chunk)
    return bytes(buf)


# ── Streaming session (one WS per turn) ─────────────────────────────────────

class TtsLiveSession:
    """
    One DashScope TTS WebSocket per LLM turn.
    Call open() once, then append(text) as sentences arrive, then finish().
    Consume audio via the async generator chunks().
    """

    def __init__(self):
        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._tts = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def open(self) -> None:
        """Open the TTS WebSocket. Runs blocking SDK setup in a thread pool."""
        from dashscope.audio.qwen_tts_realtime import QwenTtsRealtimeCallback

        self._loop = asyncio.get_event_loop()
        queue = self._queue
        loop = self._loop

        class _CB(QwenTtsRealtimeCallback):
            def on_open(self): logger.debug("TTS live session opened")

            def on_close(self, code, msg):
                logger.debug(f"TTS live session closed: code={code} msg={msg}")
                loop.call_soon_threadsafe(queue.put_nowait, None)

            def on_event(self, response: dict):
                try:
                    t = response.get("type", "")
                    if t != "response.audio.delta":
                        logger.debug(f"TTS live event: {t} — {str(response)[:200]}")
                    if t == "response.audio.delta":
                        raw = response.get("delta", "")
                        if raw:
                            loop.call_soon_threadsafe(queue.put_nowait, base64.b64decode(raw))
                    elif t == "session.finished":
                        loop.call_soon_threadsafe(queue.put_nowait, None)
                except Exception as e:
                    logger.error(f"TTS live callback: {e}")
                    loop.call_soon_threadsafe(queue.put_nowait, None)

        cb = _CB()
        self._tts = await asyncio.get_event_loop().run_in_executor(
            None, _connect_tts, cb
        )
        logger.debug("TTS live session ready")

    def append(self, text: str) -> None:
        """Feed text into the open session. Safe to call multiple times."""
        if not self._tts or not text.strip():
            return
        for chunk in _split_text(text):
            try:
                self._tts.append_text(chunk)
            except Exception as e:
                logger.warning(f"TTS live append error: {e}")

    def finish(self) -> None:
        """Signal end of text input. Audio will finish streaming via chunks()."""
        if self._tts:
            try:
                self._tts.finish()
            except Exception as e:
                logger.warning(f"TTS live finish error: {e}")

    async def chunks(self) -> AsyncIterator[bytes]:
        """Async generator: yield PCM audio chunks until session ends."""
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk


# ── Text splitter ────────────────────────────────────────────────────────────

def _split_text(text: str, max_len: int = 20) -> list[str]:
    import re
    parts = re.split(r'(?<=[，。！？,.!?；;：:\n])', text)
    result = []
    buf = ""
    for part in parts:
        if not part:
            continue
        buf += part
        if len(buf) >= max_len:
            result.append(buf)
            buf = ""
    if buf:
        result.append(buf)
    return result or [text]
