"""Safe redirect for Shopify App Pricing welcome links."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.api.shopify_embedded import shopify_app_pricing_welcome
from app.runtime.security import apply_security_headers
from app.services.shopify_navigation import shopify_app_pricing_welcome_url


def _request(path, query_string=""):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string.encode(),
        "headers": [(b"host", b"api.diaglob.tech")],
        "client": ("127.0.0.1", 12345),
        "server": ("api.diaglob.tech", 443),
    })


def test_private_plan_return_reaches_frontend_billing_workspace(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")

    result = shopify_app_pricing_welcome_url("plan_handle=diaglob-poc-test")

    assert result == "https://diaglob.tech/app/plans?plan_handle=shopify-hosted-return"


def test_private_plan_http_callback_redirects_to_billing_workspace(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")

    response = shopify_app_pricing_welcome(_request(
        "/app/plans",
        "plan_handle=diaglob-poc-test&shop=diaglob-poc.myshopify.com"
        "&charge_id=75962974399",
    ))

    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://diaglob.tech/app/plans?plan_handle=shopify-hosted-return"
    )
    assert response.headers["cache-control"] == "no-store"


def test_plan_welcome_url_does_not_forward_untrusted_return_values(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")

    result = shopify_app_pricing_welcome_url(
        "plan_handle=diaglob-poc-test&shop=attacker.myshopify.com"
        "&return_to=https%3A%2F%2Fevil.example",
    )

    assert "attacker" not in result
    assert "evil.example" not in result
    assert result == "https://diaglob.tech/app/plans?plan_handle=shopify-hosted-return"


def test_pricing_return_fails_closed_when_frontend_origin_is_not_safe(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://attacker.example/redirect")

    with pytest.raises(HTTPException) as raised:
        shopify_app_pricing_welcome(_request("/app/plans", "plan_handle=starter"))

    assert raised.value.status_code == 503


def test_pricing_return_security_headers_allow_shopify_admin_only():
    response = RedirectResponse(
        "https://diaglob.tech/app/plans",
        status_code=302,
    )

    apply_security_headers("/app/plans", b"", response)

    assert response.headers["content-security-policy"].startswith(
        "frame-ancestors https://admin.shopify.com;",
    )
    assert "x-frame-options" not in response.headers


def test_plan_welcome_url_fails_closed_for_unsafe_frontend_origin(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://attacker.example/redirect")

    with pytest.raises(ValueError, match="FRONTEND_URL_NOT_SAFE"):
        shopify_app_pricing_welcome_url("plan_handle=diaglob-poc-test")
