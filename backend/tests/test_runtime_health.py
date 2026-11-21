from contextlib import contextmanager

from app.services.runtime_health import readiness_payload


class Connection:
    def execute(self, _statement):
        return None


@contextmanager
def connected():
    yield Connection()


@contextmanager
def disconnected():
    raise RuntimeError("database unavailable")
    yield  # pragma: no cover


def test_readiness_reports_a_connected_database_without_driver_details():
    assert readiness_payload(connected) == {
        "status": "ok",
        "service": "diaglob-api",
        "database": "connected",
        "multitenant": True,
        "multistore": True,
    }


def test_readiness_fails_closed_without_exposing_connection_error():
    assert readiness_payload(disconnected) == {
        "status": "degraded",
        "service": "diaglob-api",
        "database": "error",
        "multitenant": True,
        "multistore": True,
    }
