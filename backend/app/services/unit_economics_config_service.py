"""Store-scoped Unit Economics configuration service."""

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from ..models import PaymentMethodCostRule, Store, StoreUnitEconomicsConfig


DEFAULT_MONEY_FIELDS = (
    "outbound_shipping_cost",
    "return_logistics_cost",
    "default_payment_fee_fixed",
)
DEFAULT_PERCENT_FIELDS = (
    "default_payment_fee_percent",
    "default_cod_fee_percent",
)
MAX_PAYMENT_METHOD_LENGTH = 50
MAX_MONEY_VALUE = Decimal("99999999999999.9999")


def normalize_payment_method(value: str | None) -> str:
    """Normalize provider/payment labels to a stable matching key."""
    return (value or "").strip().casefold()


def _load_owned_store(
    db: Session,
    organization_id: int,
    store_id: int,
) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        raise ValueError("store_not_found")
    return store


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid_unit_economics_value") from exc
    if not result.is_finite():
        raise ValueError("invalid_unit_economics_value")
    return result


def _validate_money(value: Any) -> Decimal | None:
    result = _as_decimal(value)
    if result is not None and (result < 0 or result > MAX_MONEY_VALUE):
        raise ValueError("invalid_unit_economics_value")
    return result


def _validate_percent(value: Any) -> Decimal | None:
    result = _as_decimal(value)
    if result is not None and (result < 0 or result > 100):
        raise ValueError("invalid_unit_economics_value")
    return result


def _validate_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("invalid_unit_economics_value")


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _serialize_rule(rule: PaymentMethodCostRule) -> dict[str, Any]:
    return {
        "payment_method": rule.payment_method,
        "fee_percent": _number(rule.fee_percent),
        "fee_fixed": _number(rule.fee_fixed),
        "is_cod": bool(rule.is_cod),
        "cod_fee_percent": _number(rule.cod_fee_percent),
    }


def _empty_dto(store: Store) -> dict[str, Any]:
    return {
        "store_id": store.id,
        "currency": store.currency,
        "outbound_shipping_cost": None,
        "return_logistics_cost": None,
        "default_payment_fee_percent": None,
        "default_payment_fee_fixed": None,
        "default_cod_fee_percent": None,
        "payment_methods": [],
    }


def _serialize_config(
    store: Store,
    config: StoreUnitEconomicsConfig | None,
) -> dict[str, Any]:
    if config is None:
        return _empty_dto(store)

    rules = sorted(
        config.payment_method_rules,
        key=lambda rule: (rule.payment_method, rule.id or 0),
    )
    return {
        "store_id": store.id,
        "currency": store.currency,
        "outbound_shipping_cost": _number(config.outbound_shipping_cost),
        "return_logistics_cost": _number(config.return_logistics_cost),
        "default_payment_fee_percent": _number(config.default_payment_fee_percent),
        "default_payment_fee_fixed": _number(config.default_payment_fee_fixed),
        "default_cod_fee_percent": _number(config.default_cod_fee_percent),
        "payment_methods": [_serialize_rule(rule) for rule in rules],
    }


def get_unit_economics_config(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict[str, Any]:
    """Read config without creating persistence as a side effect."""
    store = _load_owned_store(db, organization_id, store_id)
    config = (
        db.query(StoreUnitEconomicsConfig)
        .filter(
            StoreUnitEconomicsConfig.organization_id == organization_id,
            StoreUnitEconomicsConfig.store_id == store_id,
        )
        .first()
    )
    return _serialize_config(store, config)


def clear_fixed_unit_economics_costs(
    db: Session,
    organization_id: int,
    store_id: int,
) -> bool:
    """Clear currency-denominated assumptions without committing the transaction."""
    config = (
        db.query(StoreUnitEconomicsConfig)
        .filter(
            StoreUnitEconomicsConfig.organization_id == organization_id,
            StoreUnitEconomicsConfig.store_id == store_id,
        )
        .first()
    )
    if config is None:
        return False

    config.outbound_shipping_cost = None
    config.return_logistics_cost = None
    config.default_payment_fee_fixed = None

    (
        db.query(PaymentMethodCostRule)
        .filter(
            PaymentMethodCostRule.organization_id == organization_id,
            PaymentMethodCostRule.store_id == store_id,
            PaymentMethodCostRule.unit_economics_config_id == config.id,
        )
        .update(
            {PaymentMethodCostRule.fee_fixed: None},
            synchronize_session=False,
        )
    )
    db.flush()
    return True


def _validated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Decimal | None] = {}
    for field in DEFAULT_MONEY_FIELDS:
        defaults[field] = _validate_money(payload.get(field))
    for field in DEFAULT_PERCENT_FIELDS:
        defaults[field] = _validate_percent(payload.get(field))

    methods: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_methods = payload.get("payment_methods") or []
    if not isinstance(raw_methods, list):
        raise ValueError("invalid_unit_economics_value")

    for raw_rule in raw_methods:
        if not isinstance(raw_rule, dict):
            raise ValueError("invalid_unit_economics_value")
        payment_method = normalize_payment_method(raw_rule.get("payment_method"))
        if not payment_method:
            raise ValueError("payment_method_required")
        if len(payment_method) > MAX_PAYMENT_METHOD_LENGTH:
            raise ValueError("payment_method_too_long")
        if payment_method in seen:
            raise ValueError("duplicate_payment_method")
        seen.add(payment_method)

        is_cod = _validate_bool(raw_rule.get("is_cod", False))
        rule = {
            "payment_method": payment_method,
            "fee_percent": _validate_percent(raw_rule.get("fee_percent")),
            "fee_fixed": _validate_money(raw_rule.get("fee_fixed")),
            "is_cod": is_cod,
            "cod_fee_percent": (
                _validate_percent(raw_rule.get("cod_fee_percent"))
                if is_cod
                else None
            ),
        }
        methods.append(rule)

    return {**defaults, "payment_methods": methods}


def replace_unit_economics_config(
    db: Session,
    organization_id: int,
    store_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Fully replace one store's Unit Economics assumptions atomically."""
    store = _load_owned_store(db, organization_id, store_id)
    validated = _validated_payload(payload)

    try:
        config = (
            db.query(StoreUnitEconomicsConfig)
            .filter(
                StoreUnitEconomicsConfig.organization_id == organization_id,
                StoreUnitEconomicsConfig.store_id == store_id,
            )
            .first()
        )
        if config is None:
            config = StoreUnitEconomicsConfig(
                organization_id=organization_id,
                store_id=store_id,
            )
            db.add(config)
            db.flush()

        for field in DEFAULT_MONEY_FIELDS + DEFAULT_PERCENT_FIELDS:
            setattr(config, field, validated[field])

        (
            db.query(PaymentMethodCostRule)
            .filter(
                PaymentMethodCostRule.organization_id == organization_id,
                PaymentMethodCostRule.store_id == store_id,
                PaymentMethodCostRule.unit_economics_config_id == config.id,
            )
            .delete(synchronize_session=False)
        )
        db.flush()

        for rule in validated["payment_methods"]:
            db.add(
                PaymentMethodCostRule(
                    organization_id=organization_id,
                    store_id=store_id,
                    unit_economics_config_id=config.id,
                    payment_method=rule["payment_method"],
                    fee_percent=rule["fee_percent"],
                    fee_fixed=rule["fee_fixed"],
                    is_cod=rule["is_cod"],
                    cod_fee_percent=rule["cod_fee_percent"],
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    return get_unit_economics_config(db, organization_id, store_id)
