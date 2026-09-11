"""Paddle implementation of the provider-neutral billing contract."""
from __future__ import annotations

import os

from .. import billing, paddle_client
from .base import (
    BillingProvider,
    BillingProviderConfigurationError,
    BillingProviderError,
)


class PaddleBillingProvider(BillingProvider):
    name = "paddle"
    webhook_signature_header = "Paddle-Signature"

    def is_configured(self) -> bool:
        return bool((os.getenv("PADDLE_API_KEY") or "").strip())

    def get_price_id(self, plan: str, billing_period_months: int = 1) -> str:
        return billing.get_paddle_price_id(plan, billing_period_months)

    def get_plan_from_price_id(self, price_id: str) -> str | None:
        return billing.get_plan_from_price_id(price_id)

    def get_billing_period_from_price_id(self, price_id: str) -> int | None:
        return billing.get_billing_period_from_price_id(price_id)

    def get_subscription_price_id(self, data: dict) -> str | None:
        return billing.get_subscription_price_id(data)

    def create_transaction(
        self,
        *,
        price_id: str,
        organization_id: int,
        plan_key: str,
        billing_period_months: int,
    ) -> dict:
        return self._call(
            paddle_client.create_transaction,
            price_id=price_id,
            organization_id=organization_id,
            plan_key=plan_key,
            billing_period_months=billing_period_months,
        )

    def get_subscription(self, subscription_id: str) -> dict:
        return self._call(paddle_client.get_subscription, subscription_id)

    def preview_subscription_update(
        self,
        *,
        subscription_id: str,
        items: list[dict],
        proration_billing_mode: str,
        on_payment_failure: str = "prevent_change",
        next_billed_at: str | None = None,
    ) -> dict:
        return self._call(
            paddle_client.preview_subscription_update,
            subscription_id=subscription_id,
            items=items,
            proration_billing_mode=proration_billing_mode,
            on_payment_failure=on_payment_failure,
            next_billed_at=next_billed_at,
        )

    def update_subscription(
        self,
        *,
        subscription_id: str,
        items: list[dict],
        proration_billing_mode: str,
        on_payment_failure: str = "prevent_change",
        custom_data: dict | None = None,
        timeout: int = 45,
        next_billed_at: str | None = None,
    ) -> dict:
        return self._call(
            paddle_client.update_subscription,
            subscription_id=subscription_id,
            items=items,
            proration_billing_mode=proration_billing_mode,
            on_payment_failure=on_payment_failure,
            custom_data=custom_data,
            timeout=timeout,
            next_billed_at=next_billed_at,
        )

    def cancel_subscription(self, subscription_id: str) -> dict:
        return self._call(paddle_client.cancel_subscription, subscription_id)

    def resume_subscription(self, subscription_id: str) -> dict:
        return self._call(paddle_client.resume_subscription, subscription_id)

    def verify_webhook(self, raw_body: bytes, signature_header: str) -> None:
        secret = (os.getenv("PADDLE_WEBHOOK_SECRET") or "").strip()
        if not secret:
            raise BillingProviderConfigurationError(
                "Paddle webhook secret not configured"
            )
        billing.verify_paddle_signature(raw_body, signature_header, secret)

    def _call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except paddle_client.PaddleConfigError as exc:
            raise BillingProviderConfigurationError(str(exc)) from exc
        except paddle_client.PaddleProviderError as exc:
            raise BillingProviderError(
                provider=self.name,
                status_code=exc.status_code,
                detail=exc.detail,
            ) from exc
