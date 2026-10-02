"""Carrier registry and status normalization for LATAM shipments."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CarrierDefinition:
    key: str
    name: str
    countries: tuple[str, ...]
    aliases: tuple[str, ...]
    integration_modes: tuple[str, ...]
    documented_api: bool = False
    tracking_page_url: str | None = None
    tracking_url_template: str | None = None

    def serialize(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "countries": list(self.countries),
            "integration_modes": list(self.integration_modes),
            "tracking_page_url": self.tracking_page_url,
            "supports_push_webhook": "webhook" in self.integration_modes,
            "supports_direct_sync": "api" in self.integration_modes,
            "documented_api": self.documented_api,
        }


CARRIERS: dict[str, CarrierDefinition] = {
    "coordinadora": CarrierDefinition(
        key="coordinadora",
        name="Coordinadora",
        countries=("CO",),
        aliases=("coordinadora", "coordinadora mercantil"),
        integration_modes=("webhook",),
        documented_api=True,
        tracking_page_url="https://coordinadora.com/rastreo/",
        tracking_url_template="https://rastreo.coordinadora.com/?guia={tracking_number}",
    ),
    "servientrega": CarrierDefinition(
        key="servientrega",
        name="Servientrega",
        countries=("CO",),
        aliases=("servientrega", "servi entrega"),
        integration_modes=("webhook",),
        documented_api=False,
        tracking_page_url="https://www.servientrega.com/wps/portal/rastreo-envio",
    ),
    "interrapidisimo": CarrierDefinition(
        key="interrapidisimo",
        name="Inter Rapidísimo",
        countries=("CO",),
        aliases=(
            "inter rapidisimo",
            "inter rapidísimo",
            "interrapidisimo",
            "interrapidísimo",
        ),
        integration_modes=("webhook",),
        documented_api=True,
        tracking_page_url="https://www.interrapidisimo.com/",
    ),
    "tcc": CarrierDefinition(
        key="tcc",
        name="TCC",
        countries=("CO",),
        aliases=("tcc", "transportadora comercial colombia"),
        integration_modes=("webhook",),
        documented_api=True,
        tracking_page_url="https://tcc.com.co/",
    ),
}


CANONICAL_STATUSES = {
    "PENDING",
    "SHIPPED",
    "IN_TRANSIT",
    "CUSTOMS",
    "OUT_FOR_DELIVERY",
    "READY_FOR_PICKUP",
    "DELIVERED",
    "DELAYED",
    "FAILED",
    "EXCEPTION",
    "RETURNED",
}


def _normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def get_carrier(carrier_key: str) -> CarrierDefinition | None:
    return CARRIERS.get(_normalize_text(carrier_key).replace(" ", ""))


def list_carriers(country_code: str | None = None) -> list[dict]:
    country = str(country_code or "").strip().upper()
    carriers: Iterable[CarrierDefinition] = CARRIERS.values()
    if country:
        carriers = [carrier for carrier in carriers if country in carrier.countries]
    return [carrier.serialize() for carrier in carriers]


def detect_carrier(
    *,
    carrier_hint: str | None = None,
    tracking_number: str | None = None,
) -> dict:
    """Detect conservatively. Prefer explicit carrier names over number guessing."""
    normalized_hint = _normalize_text(carrier_hint)
    if normalized_hint:
        for carrier in CARRIERS.values():
            aliases = {_normalize_text(alias) for alias in carrier.aliases}
            if normalized_hint in aliases:
                return {
                    "carrier_key": carrier.key,
                    "carrier_name": carrier.name,
                    "confidence": 1.0,
                    "source": "carrier_hint",
                }
            if any(alias and alias in normalized_hint for alias in aliases):
                return {
                    "carrier_key": carrier.key,
                    "carrier_name": carrier.name,
                    "confidence": 0.9,
                    "source": "carrier_hint_partial",
                }

    # Tracking-number-only detection is intentionally conservative because
    # Colombian carriers can have overlapping numeric guide formats.
    tracking = re.sub(r"\s+", "", str(tracking_number or ""))
    if tracking:
        return {
            "carrier_key": None,
            "carrier_name": None,
            "confidence": 0.0,
            "source": "tracking_number_ambiguous",
        }

    return {
        "carrier_key": None,
        "carrier_name": None,
        "confidence": 0.0,
        "source": "unknown",
    }


def tracking_url(carrier_key: str, tracking_number: str) -> str | None:
    carrier = get_carrier(carrier_key)
    if carrier is None:
        return None
    if carrier.tracking_url_template:
        return carrier.tracking_url_template.format(
            tracking_number=tracking_number,
        )
    return carrier.tracking_page_url


def normalize_carrier_status(
    raw_status: str | None,
    raw_label: str | None = None,
) -> str:
    explicit = str(raw_status or "").strip().upper().replace(" ", "_")
    if explicit in CANONICAL_STATUSES:
        return explicit

    value = _normalize_text(raw_label or raw_status)
    if not value:
        return "PENDING"

    rules = (
        ("DELIVERED", ("entregado", "delivered", "entrega realizada")),
        (
            "OUT_FOR_DELIVERY",
            (
                "en reparto",
                "ruta de entrega",
                "salio a reparto",
                "out for delivery",
            ),
        ),
        (
            "READY_FOR_PICKUP",
            (
                "listo para recoger",
                "disponible para recoger",
                "ready for pickup",
                "ready for pick up",
            ),
        ),
        ("CUSTOMS", ("aduana", "customs")),
        ("RETURNED", ("devuelto", "devolucion", "retornado", "returned")),
        ("DELAYED", ("retraso", "retrasado", "demora", "delayed")),
        (
            "FAILED",
            (
                "entrega fallida",
                "no entregado",
                "failed delivery",
                "delivery failed",
            ),
        ),
        (
            "EXCEPTION",
            (
                "novedad",
                "incidencia",
                "exception",
                "direccion incorrecta",
                "destinatario ausente",
            ),
        ),
        ("SHIPPED", ("despachado", "enviado", "shipped", "dispatch")),
        (
            "IN_TRANSIT",
            (
                "en transito",
                "transito",
                "transportando",
                "en transporte",
                "in transit",
            ),
        ),
    )
    for canonical, phrases in rules:
        if any(_normalize_text(phrase) in value for phrase in phrases):
            return canonical
    return "IN_TRANSIT"
