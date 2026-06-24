import asyncio
import base64

import pytest

from app.audio import tts as tts_module
from app.audio.tts import TtsLiveSession


@pytest.mark.asyncio
async def test_live_session_audio_delta_reaches_chunk_queue(monkeypatch):
    payload = b"pcm-bytes"

    def fake_connect_tts(callback):
        callback.on_event(
            {
                "type": "response.audio.delta",
                "delta": base64.b64encode(payload).decode("ascii"),
            }
        )
        return object()

    monkeypatch.setattr(tts_module, "_connect_tts", fake_connect_tts)

    session = TtsLiveSession()
    await session.open()

    chunks = session.chunks()
    chunk = await asyncio.wait_for(anext(chunks), timeout=1)

    assert chunk == payload
    assert session._first_audio_at > 0
