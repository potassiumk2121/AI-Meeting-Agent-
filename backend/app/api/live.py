import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.errors import AppError
from app.hub import hub
from app.services.pipeline import ingest_chat, ingest_utterance

router = APIRouter(prefix="/api/meetings", tags=["live"])


@router.websocket("/{meeting_id}/live")
async def live(websocket: WebSocket, meeting_id: uuid.UUID) -> None:
    await websocket.accept()
    room = str(meeting_id)
    hub.join(room, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "message": "Invalid message"})
                continue
            kind = message.get("type")
            try:
                if kind == "ping":
                    await websocket.send_json({"type": "pong"})
                elif kind == "utterance":
                    async with SessionLocal() as session:
                        await ingest_utterance(
                            session,
                            meeting_id,
                            speaker=str(message.get("speaker") or ""),
                            text=str(message.get("text") or ""),
                            language=message.get("language"),
                            timestamp_label=message.get("timestamp_label"),
                            source="live",
                        )
                elif kind == "chat":
                    async with SessionLocal() as session:
                        await ingest_chat(
                            session,
                            meeting_id,
                            sender=str(message.get("sender") or message.get("speaker") or ""),
                            text=str(message.get("text") or ""),
                            language=message.get("language"),
                            timestamp_label=message.get("timestamp_label"),
                        )
                else:
                    await websocket.send_json({"type": "error", "message": "Unknown message type"})
            except AppError as exc:
                await websocket.send_json({"type": "error", "message": exc.message})
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room, websocket)
