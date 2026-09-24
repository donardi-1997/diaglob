"""CJ API client tests."""

from datetime import datetime

import pytest

from app.integrations.cj import client as cj


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response, calls, **_kwargs):
        self.response = response
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def install_fake_client(monkeypatch, response):
    calls = []

    def factory(**kwargs):
        return FakeClient(response, calls, **kwargs)

    monkeypatch.setattr(cj.httpx, "Client", factory)
    return calls


def test_get_access_token_uses_documented_endpoint(monkeypatch):
    calls = install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {
                "code": 200,
                "data": {
                    "openId": 123,
                    "accessToken": "access",
                    "refreshToken": "refresh",
                    "accessTokenExpiryDate": "2027-03-23T10:00:00+00:00",
                    "refreshTokenExpiryDate": "2027-03-23T10:00:00+00:00",
                },
            },
        ),
    )

    result = cj.get_access_token("api-key")

    assert result["accessToken"] == "access"
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/authentication/getAccessToken")
    assert calls[0][2]["json"] == {"apiKey": "api-key"}


def test_provider_code_auth_error_is_normalized(monkeypatch):
    install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {"code": 1600005, "message": "APIkey is wrong", "data": None},
        ),
    )

    with pytest.raises(cj.CJAuthError) as exc:
        cj.get_access_token("bad-key")

    assert exc.value.code == 1600005


def test_get_settings_sends_cj_access_token_header(monkeypatch):
    calls = install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {"code": 200, "data": {"openId": 7, "openName": "Demo"}},
        ),
    )

    result = cj.get_settings("secret-token")

    assert result["openId"] == 7
    assert calls[0][2]["headers"]["CJ-Access-Token"] == "secret-token"


def test_parse_cj_datetime_normalizes_to_naive_utc():
    parsed = cj.parse_cj_datetime("2026-09-24T20:00:00+08:00")

    assert parsed == datetime(2026, 9, 24, 12, 0, 0)


def test_list_products_uses_v2_search_endpoint(monkeypatch):
    calls = install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {"code": 200, "data": {"content": [], "totalRecords": 0}},
        ),
    )

    cj.list_products("token", query="hoodie", limit=25, page=2)

    assert calls[0][1].endswith("/product/listV2")
    assert calls[0][2]["params"] == {
        "page": 2,
        "size": 25,
        "keyWord": "hoodie",
    }


def test_calculate_freight_maps_variant_ids(monkeypatch):
    calls = install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {
                "code": 200,
                "data": [
                    {
                        "logisticName": "USPS+",
                        "logisticPrice": 4.71,
                        "logisticAging": "2-5",
                    }
                ],
            },
        ),
    )

    result = cj.calculate_freight(
        "token",
        start_country_code="CN",
        end_country_code="US",
        zip_code="10001",
        products=[{"variant_id": "vid-1", "quantity": 2}],
    )

    assert result[0]["logisticName"] == "USPS+"
    assert calls[0][1].endswith("/logistic/freightCalculate")
    assert calls[0][2]["json"] == {
        "startCountryCode": "CN",
        "endCountryCode": "US",
        "zip": "10001",
        "products": [{"vid": "vid-1", "quantity": 2}],
    }


def test_create_order_v3_uses_explicit_payload(monkeypatch):
    calls = install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {
                "code": 200,
                "data": {
                    "orderId": "cj-1",
                    "orderNumber": "DG-1-1",
                    "orderStatus": "CREATED",
                },
            },
        ),
    )
    body = {
        "orderNumber": "DG-1-1",
        "payType": 3,
        "isSandbox": 1,
        "products": [{"vid": "vid-1", "quantity": 1}],
    }

    result = cj.create_order_v3("token", body)

    assert result["orderId"] == "cj-1"
    assert calls[0][1].endswith("/shopping/order/createOrderV3")
    assert calls[0][2]["json"] == body


def test_get_order_accepts_custom_order_number(monkeypatch):
    calls = install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {
                "code": 200,
                "data": {
                    "orderId": "cj-1",
                    "orderNum": "DG-1-1",
                    "orderStatus": "CREATED",
                },
            },
        ),
    )

    cj.get_order("token", "DG-1-1", features=["LOGISTICS_TIMELINESS"])

    assert calls[0][2]["params"] == {
        "orderId": "DG-1-1",
        "features": ["LOGISTICS_TIMELINESS"],
    }
