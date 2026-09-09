from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.payments.base import PaymentStatus
from app.payments.mercado_pago import MercadoPagoPixProvider
from app.payments.registry import get_provider, get_providers_for_market


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class TestMercadoPagoPixRegistry:
    def test_pix_provider_is_brazil_brl_only(self):
        provider = get_provider("mercado_pago")
        assert provider is not None
        assert provider.supported_payment_methods == ["pix"]
        assert provider.is_available("BR", "BRL") is True
        assert provider.is_available("CO", "COP") is False
        assert provider.is_available("BR", "USD") is False

    def test_brazil_registry_exposes_pix(self):
        providers = get_providers_for_market("BR", "BRL")
        methods = {
            method
            for provider in providers
            for method in provider.supported_payment_methods
        }
        assert "pix" in methods
        assert "nequi_push" not in methods


class TestMercadoPagoPixProvider:
    @pytest.mark.asyncio
    async def test_create_pix_sends_idempotency_and_returns_qr(self):
        provider = MercadoPagoPixProvider()
        response = _Response(
            201,
            {
                "id": 123456,
                "status": "pending",
                "date_of_expiration": "2026-09-09T20:30:00-03:00",
                "point_of_interaction": {
                    "transaction_data": {
                        "qr_code": "000201PIX-CODE",
                        "qr_code_base64": "BASE64PNG",
                        "ticket_url": "https://www.mercadopago.com.br/payments/123/ticket",
                    }
                },
            },
        )

        client = AsyncMock()
        client.post.return_value = response
        cm = AsyncMock()
        cm.__aenter__.return_value = client
        cm.__aexit__.return_value = False

        with patch("app.payments.mercado_pago.httpx.AsyncClient", return_value=cm):
            result = await provider.create_payment(
                credentials={"client_secret": "APP_USR-test-token"},
                environment="sandbox",
                amount=Decimal("49.90"),
                currency="BRL",
                customer_phone="+5511999999999",
                description="Order #10",
                idempotency_key="idem-pix-1",
                metadata={
                    "customer_email": "buyer@example.com",
                    "customer_document": "191.191.191-00",
                    "customer_document_type": "CPF",
                },
            )

        assert result.provider_transaction_id == "123456"
        assert result.status == PaymentStatus.PENDING
        assert result.payment_method == "pix"
        assert result.requires_action is True
        assert result.action_data["qr_code"] == "000201PIX-CODE"

        kwargs = client.post.await_args.kwargs
        assert kwargs["headers"]["X-Idempotency-Key"] == "idem-pix-1"
        assert kwargs["json"]["payment_method_id"] == "pix"
        assert kwargs["json"]["payer"]["identification"] == {
            "type": "CPF",
            "number": "19119119100",
        }

    @pytest.mark.asyncio
    async def test_create_pix_requires_email(self):
        provider = MercadoPagoPixProvider()
        with pytest.raises(ValueError, match="customer_email"):
            await provider.create_payment(
                credentials={"client_secret": "APP_USR-test-token"},
                environment="sandbox",
                amount=Decimal("10"),
                currency="BRL",
                customer_phone="+5511999999999",
                description="Payment",
                idempotency_key="idem-pix-2",
                metadata={"customer_document": "19119119100"},
            )

    @pytest.mark.asyncio
    async def test_create_pix_requires_valid_cpf_shape(self):
        provider = MercadoPagoPixProvider()
        with pytest.raises(ValueError, match="CPF"):
            await provider.create_payment(
                credentials={"client_secret": "APP_USR-test-token"},
                environment="sandbox",
                amount=Decimal("10"),
                currency="BRL",
                customer_phone="+5511999999999",
                description="Payment",
                idempotency_key="idem-pix-3",
                metadata={
                    "customer_email": "buyer@example.com",
                    "customer_document": "123",
                },
            )

    @pytest.mark.asyncio
    async def test_status_mapping_approved_is_paid(self):
        provider = MercadoPagoPixProvider()
        response = _Response(
            200,
            {
                "id": 123456,
                "status": "approved",
                "date_approved": "2026-09-09T20:00:00-03:00",
            },
        )
        client = AsyncMock()
        client.get.return_value = response
        cm = AsyncMock()
        cm.__aenter__.return_value = client
        cm.__aexit__.return_value = False
        with patch("app.payments.mercado_pago.httpx.AsyncClient", return_value=cm):
            result = await provider.get_payment_status(
                {"client_secret": "APP_USR-test-token"},
                "sandbox",
                "123456",
            )
        assert result.status == PaymentStatus.PAID
