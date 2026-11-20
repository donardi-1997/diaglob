from fastapi import APIRouter, Response

from ..db import engine
from ..services.runtime_health import readiness_payload

router = APIRouter()


@router.get("/")
def root():
    return {
        "name": "Diaglob API",
        "version": "0.5.0",
    }


@router.get("/health")
@router.get("/health/ready")
def readiness(response: Response):
    """Readiness: API traffic is safe only when the database is reachable."""
    payload = readiness_payload(engine.connect)
    if payload["status"] != "ok":
        response.status_code = 503
    return payload


@router.get("/health/live")
def liveness():
    """Liveness deliberately avoids dependencies so restarts are not amplified."""
    return {"status": "ok", "service": "diaglob-api"}
