"""Public CJ webhook receiver."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.cj_webhooks import (
    CJWebhookAuthError,
    CJWebhookError,
    process_cj_webhook,
)

router = APIRouter()


@router.post("/api/webhooks/cj")
async def receive_cj_webhook(
    request: Request,
    sign: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    try:
        process_cj_webhook(
            db,
            raw_body=raw_body,
            signature=sign,
        )
    except CJWebhookAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except CJWebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # CJ only requires a successful HTTP 200 response. Keep this endpoint
    # intentionally small because webhook delivery has a three-second timeout.
    return {
        "code": 200,
        "result": "success",
        "message": "ok",
    }
