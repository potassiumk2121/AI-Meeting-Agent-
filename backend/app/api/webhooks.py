import logging
import re

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.config import get_settings
from app.database import SessionLocal
from app.services.pipeline import sync_by_external_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _process(payload: dict) -> None:
    settings = get_settings()
    for item in payload.get("value") or []:
        if settings.webhook_secret and item.get("clientState") != settings.webhook_secret:
            continue
        resource = str(item.get("resource") or "")
        match = re.search(r"onlineMeetings(?:\(|/)([^)/]+)", resource, re.IGNORECASE)
        if not match:
            continue
        try:
            async with SessionLocal() as session:
                await sync_by_external_id(session, match.group(1))
        except Exception:
            logger.exception("graph notification sync failed")


@router.api_route("/graph", methods=["GET", "POST"])
async def graph_webhook(
    request: Request,
    background: BackgroundTasks,
    validationToken: str | None = None,
):
    if validationToken:
        return Response(content=validationToken, media_type="text/plain")
    if request.method == "GET":
        return Response(status_code=200)
    payload = await request.json()
    background.add_task(_process, payload)
    return Response(status_code=202)
