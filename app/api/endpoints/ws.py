"""
WebSocket endpoint for real-time audio streaming.

URL: ws://<host>/api/v1/ws/audio/{session_id}

Binary frames  → raw PCM 16kHz 16bit mono audio chunks
Text frames    → JSON control messages (see handler.py for protocol)
"""
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.audio.handler import get_or_create_handler, remove_handler
from app.core.session_store import get_session_store

router = APIRouter()


@router.websocket("/audio/{session_id}")
async def audio_stream(websocket: WebSocket, session_id: str):
    """
    Bidirectional real-time audio stream.

    The session must be created first via POST /api/v1/interview/start,
    which initializes the LangGraph state and stores it in the session store.
    """
    store = get_session_store()

    # Reject if session doesn't exist
    if not await store.exists(session_id):
        await websocket.close(code=4404, reason="Session not found")
        return

    await websocket.accept()
    logger.info(f"WS connected: session={session_id}")

    handler = get_or_create_handler(session_id)
    await handler.attach(websocket)

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                # Binary frame — raw PCM audio
                await handler.handle_audio(message["bytes"])

            elif "text" in message and message["text"]:
                # Text frame — control message
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")
                if msg_type == "end_speech":
                    await handler.handle_end_speech()
                elif msg_type == "tts_begin":
                    await handler.handle_tts_begin()
                elif msg_type == "tts_append":
                    await handler.handle_tts_append(data.get("text", ""))
                elif msg_type == "tts_finish":
                    await handler.handle_tts_finish()
                elif msg_type == "ping":
                    await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: session={session_id}")
    except Exception as e:
        logger.exception(f"WS error session={session_id}: {e}")
    finally:
        await handler.detach()
        remove_handler(session_id)
