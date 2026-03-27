"""
ASR client — DashScope paraformer-realtime-v2 (streaming).

Usage:
    asr = StreamingASR()
    await asr.start()
    await asr.send(pcm_chunk)          # call for each audio chunk
    await asr.stop()
    transcript = await asr.get_final() # blocks until final result
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from app.config import get_settings

settings = get_settings()


@dataclass
class ASRResult:
    text: str
    is_final: bool
    sentence_end: bool = False


class StreamingASR:
    """
    Wraps DashScope Recognition in a simple async interface.

    Audio format expected: PCM 16kHz 16-bit mono.
    """

    def __init__(self):
        self._recognition = None
        self._partial_queue: asyncio.Queue[ASRResult] = asyncio.Queue()
        self._final_text: str = ""
        self._last_partial: str = ""   # fallback if sentence_end never fires
        self._done = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        try:
            from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
        except ImportError:
            logger.error("dashscope not installed — cannot use ASR")
            return

        self._loop = asyncio.get_event_loop()
        partial_queue = self._partial_queue
        done_event = self._done
        loop = self._loop
        store = self  # capture self for callback

        class _Callback(RecognitionCallback):
            def on_open(self) -> None:
                logger.info("ASR connection opened")

            def on_close(self) -> None:
                logger.info("ASR connection closed")
                # Always unblock stop() — on_complete may not fire on error/timeout
                loop.call_soon_threadsafe(done_event.set)

            def on_complete(self) -> None:
                logger.info(f"ASR complete, final text: '{store._final_text}'")
                loop.call_soon_threadsafe(done_event.set)

            def on_error(self, result: RecognitionResult) -> None:
                # NO_VALID_AUDIO_ERROR is expected when session times out with no audio
                if "NO_VALID_AUDIO_ERROR" in str(result):
                    logger.debug(f"ASR session closed (no audio received): {result}")
                else:
                    logger.error(f"ASR error: {result}")
                loop.call_soon_threadsafe(done_event.set)

            def on_event(self, result: RecognitionResult) -> None:
                logger.debug(f"ASR on_event raw output: {result.output}")
                if not result.output:
                    return
                # DashScope may return sentence as a dict OR a list of dicts
                raw = result.output.get("sentence", None)
                if raw is None:
                    return
                sentences = raw if isinstance(raw, list) else [raw]
                for sentence in sentences:
                    text = sentence.get("text", "")
                    is_final = sentence.get("sentence_end", False)
                    logger.debug(f"ASR sentence: text='{text}' is_final={is_final}")
                    if text:
                        store._last_partial = text  # always keep latest
                        asr_result = ASRResult(
                            text=text,
                            is_final=is_final,
                            sentence_end=is_final,
                        )
                        if is_final:
                            store._final_text += text  # accumulate across sentence boundaries
                        loop.call_soon_threadsafe(
                            partial_queue.put_nowait, asr_result
                        )

        self._recognition = Recognition(
            model=settings.asr_model_name,
            format="pcm",
            sample_rate=16000,
            language_hints=["zh", "en"],
            callback=_Callback(),
            api_key=settings.dashscope_api_key,
        )
        self._recognition.start()
        logger.info("StreamingASR started")

    async def send(self, pcm_chunk: bytes) -> None:
        """Feed raw PCM audio chunk to ASR."""
        if self._recognition:
            try:
                self._recognition.send_audio_frame(pcm_chunk)
            except Exception as e:
                # DashScope raises InvalidParameter when recognition stops itself
                # after detecting sentence end — safe to ignore
                logger.debug(f"ASR send ignored (recognition stopped): {e}")

    async def stop(self) -> None:
        """Signal end of audio and wait for final result."""
        if self._recognition:
            self._recognition.stop()
            try:
                await asyncio.wait_for(self._done.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("ASR stop timed out — no on_complete received (no audio data?)")
                self._done.set()  # unblock any waiters

    async def get_partial(self, timeout: float = 0.05) -> Optional[ASRResult]:
        """Non-blocking poll for a partial/final result from the ASR stream."""
        try:
            return await asyncio.wait_for(self._partial_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    @property
    def is_closed(self) -> bool:
        """True if this session ended (either via stop() or DashScope auto-close)."""
        return self._done.is_set()

    @property
    def final_text(self) -> str:
        # Use confirmed final; fall back to last partial if sentence_end never fired
        return self._final_text or self._last_partial
