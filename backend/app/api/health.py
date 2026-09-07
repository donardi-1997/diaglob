from fastapi import APIRouter

from ..db import engine

router = APIRouter()


@router.get("/")
def root():
    return {
        "name": "Diaglob API",
        "version": "0.5.0",
    }


@router.get("/health")
def health():
    db_status = "disconnected"

    try:
        with engine.connect() as conn:
            conn.execute(
                __import__(
                    "sqlalchemy",
                    fromlist=["text"],
                ).text("SELECT 1")
            )
            db_status = "connected"
    except Exception:
        db_status = "error"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "service": "diaglob-api",
        "database": db_status,
        "multitenant": True,
        "multistore": True,
    }
