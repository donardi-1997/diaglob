"""Public CJ webhook receiver."""

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.auto_fulfillment import sync_shopify_from_shipment_background
from ..services.cj_webhooks import (
    CJWebhookAuthError,
    CJWebhookError,
    process_cj_webhook,
)

router = APIRouter()


@router.post("/api/webhooks/cj")
async def receive_cj_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    sign: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    try:
        result = process_cj_webhook(
            db,
            raw_body=raw_body,
            signature=sign,
        )
    except CJWebhookAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except CJWebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    shipment_id = result.get("shipment_id")
    if shipment_id:
        background_tasks.add_task(
            sync_shopify_from_shipment_background,
            int(shipment_id),
        )

    # CJ only requires a successful HTTP 200 response. Keep this endpoint
    # intentionally small because webhook delivery has a three-second timeout.
    return {
        "code": 200,
        "result": "success",
        "message": "ok",
    }
