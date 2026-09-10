import pytest

from app import billing, paddle_client


def test_paddle_defaults_to_sandbox(monkeypatch):
    monkeypatch.delenv("PADDLE_ENVIRONMENT", raising=False)
    assert paddle_client.get_paddle_environment() == "sandbox"
    assert paddle_client.get_paddle_base_url() == "https://sandbox-api.paddle.com"


def test_paddle_production_base_url(monkeypatch):
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    assert paddle_client.get_paddle_base_url() == "https://api.paddle.com"


def test_paddle_rejects_unknown_environment(monkeypatch):
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "staging")
    with pytest.raises(paddle_client.PaddleConfigError, match="sandbox.*production"):
        paddle_client.get_paddle_environment()


def test_paddle_config_error_is_provider_503():
    error = paddle_client.PaddleConfigError("bad Paddle configuration")
    assert isinstance(error, paddle_client.PaddleProviderError)
    assert error.status_code == 503
    assert error.detail == {"message": "bad Paddle configuration"}


def test_paddle_rejects_sandbox_key_in_production(monkeypatch):
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_apikey_example")
    with pytest.raises(paddle_client.PaddleConfigError, match="Sandbox Paddle API key"):
        paddle_client.get_paddle_headers()


def test_paddle_rejects_live_key_in_sandbox(monkeypatch):
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_live_apikey_example")
    with pytest.raises(paddle_client.PaddleConfigError, match="Live Paddle API key"):
        paddle_client.get_paddle_headers()


def test_paddle_headers_pin_api_version(monkeypatch):
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_live_apikey_example")
    headers = paddle_client.get_paddle_headers()
    assert headers["Paddle-Version"] == "1"
    assert headers["Authorization"] == "Bearer pdl_live_apikey_example"


def test_live_price_resolution_never_falls_back_to_csv(monkeypatch):
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    monkeypatch.delenv("PADDLE_PRICE_STARTER_1M", raising=False)
    monkeypatch.delenv("PADDLE_PRICE_STARTER", raising=False)
    monkeypatch.setattr(
        billing,
        "CSV_PADDLE_PRICE_IDS",
        {"starter": {1: "pri_sandbox_from_csv"}},
    )

    assert billing.resolve_paddle_price(
        "starter", 1, "PADDLE_PRICE_STARTER"
    ) is None
