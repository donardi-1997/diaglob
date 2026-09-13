# Dropshipping Analytics V2.2 — Unit Economics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add honest store-level contribution economics using actual data first, configured estimates second, and explicit incomplete states whenever an applicable cost is unknown.

**Architecture:** Persist per-store financial assumptions in dedicated Unit Economics models, expose configuration through a store-scoped service/API, resolve exact-period Meta spend separately, and compute contribution economics in a read-only analytics service. Frontend Settings owns editing; Dropshipping Analytics consumes the read-only result as an independently failing dashboard section.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, Meta Graph client, React 19, TypeScript 6, Axios, node:test, Vite.

**Spec:** `docs/superpowers/specs/2026-09-11-dropshipping-unit-economics-v2-2-design.md`

## Global Constraints

- Cost resolution is real-first with configurable estimated fallbacks.
- Cost provenance is explicit: `actual`, `estimated`, `missing`, or `not_applicable`.
- Advertising spend is store-level only; never allocate it to products in V2.2.
- No FX conversion.
- Meta Ads must be `missing` when disconnected, unavailable, unbounded, currency-unknown, or currency-mismatched.
- A numeric zero never proves availability; availability comes from resolver state.
- If any applicable mandatory component is missing, `contribution_profit` and `contribution_margin` are `null`.
- Existing gross-profit/Product Analytics V2 semantics remain unchanged.
- Returned orders recognize zero revenue and zero recoverable COGS, but may incur outbound and reverse-logistics costs.
- Cancelled orders recognize zero revenue and no invented shipping, COGS, or payment costs.
- Business logic belongs in `backend/app/services/`, not routers.
- Preserve tenant isolation with `organization_id + store_id` on every read/write.
- Settings is the only editable source of Unit Economics assumptions.

---

## File Structure

### Backend create
- `backend/app/model_domains/unit_economics.py` — persistence models only.
- `backend/alembic/versions/n0b1c2d3e4f5_add_unit_economics_config.py` — schema migration, revising current head `m9a0b1c2d3e4`.
- `backend/app/services/unit_economics_config_service.py` — config validation, normalization, replacement, currency-change clearing.
- `backend/app/services/unit_economics_meta.py` — exact-range Meta spend resolution and provenance.
- `backend/app/services/dropshipping_unit_economics.py` — read-only financial calculation engine.
- `backend/app/api/unit_economics.py` — GET/PUT configuration endpoints only.
- `backend/tests/test_unit_economics_models.py`
- `backend/tests/test_unit_economics_config_service.py`
- `backend/tests/test_unit_economics_config_api.py`
- `backend/tests/test_unit_economics_meta.py`
- `backend/tests/test_dropshipping_unit_economics.py`
- `backend/tests/test_dropshipping_unit_economics_api.py`

### Backend modify
- `backend/app/models.py` — compatibility re-export of Unit Economics models only.
- `backend/app/main.py` — register config router.
- `backend/app/api/stores.py` — call currency-change clearing service inside existing store-update transaction.
- `backend/app/api/dropshipping_analytics.py` — add read-only Unit Economics analytics endpoint.
- `backend/tests/test_route_contract.py` and `backend/tests/contracts/api_routes.json` — regenerate strict API route snapshot including V2.1 and V2.2 routes.

### Frontend create
- `frontend/src/services/unitEconomics.ts` — config DTOs and GET/PUT client.
- `frontend/src/components/UnitEconomicsSettingsPanel.tsx` — per-store assumptions editor.
- `frontend/src/components/DropshippingUnitEconomics.tsx` — analytics presentation.
- `frontend/src/utils/unitEconomics.ts` — locale/provenance/presentation helpers without React.
- `frontend/tests/unitEconomics.test.ts`

### Frontend modify
- `frontend/src/services/analytics.ts` — Unit Economics analytics DTO/client.
- `frontend/src/pages/StoresPage.tsx` — render Settings panel when configuring an existing store.
- `frontend/src/components/DropshippingOverview.tsx` — fetch/render sixth independent analytics section.
- `frontend/src/utils/dropshippingAnalyticsState.ts` — add `unitEconomics` section.
- `frontend/tests/dropshippingAnalyticsState.test.ts` — resilience contract.
- Existing store/analytics CSS files or one focused Unit Economics CSS file, following repository conventions discovered during implementation.

---

### Task 1: Persist Unit Economics configuration safely

**Files:**
- Create: `backend/app/model_domains/unit_economics.py`
- Create: `backend/alembic/versions/n0b1c2d3e4f5_add_unit_economics_config.py`
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_unit_economics_models.py`

**Interfaces:**
- Produces: `StoreUnitEconomicsConfig` and `PaymentMethodCostRule` SQLAlchemy models importable from `app.models`.
- Constraints: one config per store; one normalized method key per store; percentage/money validation is service-owned, while FK/unique integrity is DB-owned.

- [ ] **Step 1: Write failing model-registration tests**

```python
from app.models import PaymentMethodCostRule, StoreUnitEconomicsConfig


def test_unit_economics_tables_registered():
    assert StoreUnitEconomicsConfig.__tablename__ == "store_unit_economics_configs"
    assert PaymentMethodCostRule.__tablename__ == "payment_method_cost_rules"


def test_store_config_is_unique_per_store(db, store):
    db.add(StoreUnitEconomicsConfig(organization_id=store.organization_id, store_id=store.id))
    db.commit()
    db.add(StoreUnitEconomicsConfig(organization_id=store.organization_id, store_id=store.id))
    with pytest.raises(Exception):
        db.commit()
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `cd backend && pytest -q tests/test_unit_economics_models.py`

Expected: import/table failure because the models do not exist.

- [ ] **Step 3: Add focused persistence models**

Use the shared `Base` and define exactly these persisted fields:

```python
class StoreUnitEconomicsConfig(Base):
    __tablename__ = "store_unit_economics_configs"
    id = mapped_column(Integer, primary_key=True)
    organization_id = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    outbound_shipping_cost = mapped_column(Numeric(18, 4), nullable=True)
    return_logistics_cost = mapped_column(Numeric(18, 4), nullable=True)
    default_payment_fee_percent = mapped_column(Numeric(9, 4), nullable=True)
    default_payment_fee_fixed = mapped_column(Numeric(18, 4), nullable=True)
    default_cod_fee_percent = mapped_column(Numeric(9, 4), nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

```python
class PaymentMethodCostRule(Base):
    __tablename__ = "payment_method_cost_rules"
    __table_args__ = (UniqueConstraint("store_id", "payment_method", name="uq_unit_economics_store_payment_method"),)
    id = mapped_column(Integer, primary_key=True)
    organization_id = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_economics_config_id = mapped_column(ForeignKey("store_unit_economics_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_method = mapped_column(String(50), nullable=False)
    fee_percent = mapped_column(Numeric(9, 4), nullable=True)
    fee_fixed = mapped_column(Numeric(18, 4), nullable=True)
    is_cod = mapped_column(Boolean, default=False, nullable=False)
    cod_fee_percent = mapped_column(Numeric(9, 4), nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

Re-export these two classes from `app.models`; do not move or modify unrelated legacy models.

- [ ] **Step 4: Add migration off the verified current Alembic head**

Migration header:

```python
revision = "n0b1c2d3e4f5"
down_revision = "m9a0b1c2d3e4"
```

Create both tables, indexes/uniques matching the models, FK cascade behavior, and downgrade in reverse dependency order.

- [ ] **Step 5: Verify model and migration behavior**

Run:

```bash
cd backend
pytest -q tests/test_unit_economics_models.py
alembic upgrade head
alembic downgrade m9a0b1c2d3e4
alembic upgrade head
```

Expected: all commands succeed; exactly one Alembic head remains.

- [ ] **Step 6: Commit**

```bash
git add backend/app/model_domains/unit_economics.py backend/app/models.py backend/alembic/versions/n0b1c2d3e4f5_add_unit_economics_config.py backend/tests/test_unit_economics_models.py
git commit -m "feat: persist unit economics configuration"
```

---

### Task 2: Build the config service and store-scoped API

**Files:**
- Create: `backend/app/services/unit_economics_config_service.py`
- Create: `backend/app/api/unit_economics.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_unit_economics_config_service.py`
- Test: `backend/tests/test_unit_economics_config_api.py`

**Interfaces:**
- Produces: `normalize_payment_method(value) -> str`, `get_unit_economics_config(...) -> dict`, `replace_unit_economics_config(...) -> dict`.
- API: `GET /api/stores/{store_id}/unit-economics/config`, `PUT /api/stores/{store_id}/unit-economics/config`.

- [ ] **Step 1: Write service RED tests for normalization, field fallback data, validation, and replacement**

```python
def test_normalize_payment_method():
    assert normalize_payment_method("  Cash On Delivery  ") == "cash on delivery"


def test_replace_rejects_duplicate_normalized_methods(db, store):
    with pytest.raises(ValueError, match="duplicate_payment_method"):
        replace_unit_economics_config(
            db, store.organization_id, store.id,
            {"payment_methods": [
                {"payment_method": "COD", "is_cod": True},
                {"payment_method": " cod ", "is_cod": True},
            ]},
        )
```

Also cover negative amounts, percentages `<0` or `>100`, empty normalized methods, GET without persistence, and transactional removal of stale method rules.

- [ ] **Step 2: Run focused service tests and confirm RED**

Run: `cd backend && pytest -q tests/test_unit_economics_config_service.py`

- [ ] **Step 3: Implement minimal config service**

Use explicit helpers:

```python
def normalize_payment_method(value: str | None) -> str:
    return (value or "").strip().casefold()


def get_unit_economics_config(db: Session, organization_id: int, store_id: int) -> dict:
    ...


def replace_unit_economics_config(
    db: Session,
    organization_id: int,
    store_id: int,
    payload: dict[str, Any],
) -> dict:
    ...
```

The service validates store ownership, performs full replacement of method rules in one transaction, and returns a stable DTO including current store currency.

- [ ] **Step 4: Write API RED tests before adding routes**

Cover:
- GET empty DTO returns 200 and does not persist a config row.
- PUT requires `stores.write`.
- GET requires `stores.read`.
- foreign/deleted store returns 404.
- suspended store is readable/configurable.
- invalid numbers return 422/400 with stable detail.
- duplicate normalized methods are rejected.

Example:

```python
response = client.put(
    f"/api/stores/{store.id}/unit-economics/config",
    json={
        "outbound_shipping_cost": 15000,
        "return_logistics_cost": 18000,
        "default_payment_fee_percent": 3.5,
        "default_payment_fee_fixed": 900,
        "default_cod_fee_percent": 4,
        "payment_methods": [{
            "payment_method": "cash_on_delivery",
            "is_cod": True,
            "cod_fee_percent": 4,
        }],
    },
)
assert response.status_code == 200
assert response.json()["currency"] == "COP"
```

- [ ] **Step 5: Add Pydantic request models and thin config router**

Router calls the service only. Register `unit_economics_router` in `app.main`.

- [ ] **Step 6: Run service/API tests**

Run:

```bash
cd backend
pytest -q tests/test_unit_economics_config_service.py tests/test_unit_economics_config_api.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/unit_economics_config_service.py backend/app/api/unit_economics.py backend/app/main.py backend/tests/test_unit_economics_config_service.py backend/tests/test_unit_economics_config_api.py
git commit -m "feat: add unit economics configuration API"
```

---

### Task 3: Protect assumptions when store currency changes

**Files:**
- Modify: `backend/app/services/unit_economics_config_service.py`
- Modify: `backend/app/api/stores.py`
- Test: `backend/tests/test_unit_economics_config_service.py`
- Test: existing/new store API coverage in `backend/tests/test_stores.py` if present; otherwise `backend/tests/test_unit_economics_config_api.py`.

**Interfaces:**
- Produces: `clear_fixed_costs_for_currency_change(db, organization_id, store_id) -> None`.

- [ ] **Step 1: Add RED test for currency change**

Seed fixed and percentage assumptions, change COP -> USD, and assert:

```python
assert config.outbound_shipping_cost is None
assert config.return_logistics_cost is None
assert config.default_payment_fee_fixed is None
assert config.default_payment_fee_percent == Decimal("3.5")
assert config.default_cod_fee_percent == Decimal("4")
assert rule.fee_fixed is None
assert rule.fee_percent == Decimal("2.9")
```

- [ ] **Step 2: Run focused test and confirm failure**

Run: `cd backend && pytest -q tests/test_unit_economics_config_service.py -k currency`

- [ ] **Step 3: Implement transactional clearing and call it from existing store update**

```python
def clear_fixed_costs_for_currency_change(db, organization_id: int, store_id: int) -> None:
    config = _load_owned_config(...)
    if config is None:
        return
    config.outbound_shipping_cost = None
    config.return_logistics_cost = None
    config.default_payment_fee_fixed = None
    for rule in config.payment_method_rules:
        rule.fee_fixed = None
```

Call only when normalized new currency differs from current currency, before the existing commit.

- [ ] **Step 4: Verify store updates remain atomic**

Run store/config tests. Ensure a failed store update does not partially clear assumptions.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/unit_economics_config_service.py backend/app/api/stores.py backend/tests
git commit -m "fix: invalidate fixed costs on currency change"
```

---

### Task 4: Resolve exact-period Meta Ads spend without inventing zero

**Files:**
- Create: `backend/app/services/unit_economics_meta.py`
- Test: `backend/tests/test_unit_economics_meta.py`

**Interfaces:**
- Produces:

```python
def resolve_meta_ad_spend(
    db: Session,
    organization_id: int,
    store: Store,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    ...
```

Return shape: `amount`, `source`, `status`, `reason`, `metadata`.

- [ ] **Step 1: Write RED tests for every Meta state**

Cover exactly:
- not connected -> `missing/meta_not_connected`
- no bounded range -> `missing/bounded_date_range_required`
- unknown provider currency -> `missing/currency_unknown`
- mismatch -> `missing/currency_mismatch`
- provider error -> `missing/provider_error`
- decrypt failure -> `missing/credentials_unavailable`
- successful no-spend response -> `actual`, amount `0`
- successful spend -> `actual`, returned spend
- date-only API window `[2026-09-01, 2026-09-12)` maps to Meta `since=2026-09-01`, `until=2026-09-11`.

- [ ] **Step 2: Confirm RED**

Run: `cd backend && pytest -q tests/test_unit_economics_meta.py`

- [ ] **Step 3: Implement resolver using existing provider client**

Core date adapter:

```python
def _meta_time_range(date_from: datetime, date_to_exclusive: datetime) -> dict[str, str]:
    return {
        "since": date_from.date().isoformat(),
        "until": (date_to_exclusive.date() - timedelta(days=1)).isoformat(),
    }
```

Use existing `decrypt_secret`, `get_insights(..., time_range=...)`, and `parse_insights_row`. Do not put HTTP logic in this service.

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest -q tests/test_unit_economics_meta.py`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/unit_economics_meta.py backend/tests/test_unit_economics_meta.py
git commit -m "feat: resolve exact-period Meta ad spend"
```

---

### Task 5: Implement the deterministic Unit Economics engine

**Files:**
- Create: `backend/app/services/dropshipping_unit_economics.py`
- Test: `backend/tests/test_dropshipping_unit_economics.py`

**Interfaces:**
- Consumes: persisted config service, `resolve_meta_ad_spend`, `Order`, `OrderItem`.
- Produces:

```python
def get_store_unit_economics(
    db: Session,
    organization_id: int,
    store: Store,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    ...
```

- [ ] **Step 1: Add RED tests for lifecycle and contribution formulas**

Seed a mixed cohort and assert:

```python
assert result["recognized_revenue"] == 2500000.0
assert result["components"]["cogs"]["source"] == "actual"
assert result["components"]["outbound_shipping"]["source"] == "estimated"
assert result["components"]["reverse_logistics"]["amount"] == 36000.0
assert result["data_quality"]["status"] == "complete"
assert result["contribution_profit"] == pytest.approx(
    2500000 - 1600000 - 180000 - 92000 - 21000 - 36000 - 300000
)
```

Add independent tests for:
- returned order has zero revenue/COGS but shipping + reverse logistics;
- cancelled order has no invented costs;
- incomplete COGS with known subtotal;
- no delivered/returned orders makes shipping/payment/COD/COGS `not_applicable`;
- unresolved `payment_method` makes payment fee missing with `__missing__` metadata;
- method override fields fall back individually to defaults;
- COD is determined only by configured `is_cod`;
- missing return cost only matters when returns exist;
- negative complete contribution with zero revenue yields `contribution_margin=None`;
- any missing applicable component forces both final contribution fields to `None`;
- no NaN/Infinity.

- [ ] **Step 2: Confirm RED**

Run: `cd backend && pytest -q tests/test_dropshipping_unit_economics.py`

- [ ] **Step 3: Implement component resolvers as small pure helpers**

Use a common constructor:

```python
def _component(amount, source, status="available", reason=None, metadata=None):
    return {
        "amount": None if amount is None else float(amount),
        "source": source,
        "status": status,
        "reason": reason,
        "metadata": metadata or {},
    }
```

Keep separate helpers for COGS, outbound shipping, payment fees, COD, and returns. Use `Decimal` for arithmetic; convert at serialization boundary.

- [ ] **Step 4: Implement completeness aggregation**

```python
missing = [name for name, value in components.items() if value["status"] == "missing"]
complete = not missing
contribution_profit = None
contribution_margin = None
if complete:
    contribution_profit = recognized_revenue - sum(component_amounts)
    if recognized_revenue != 0:
        contribution_margin = contribution_profit / recognized_revenue * Decimal("100")
```

`not_applicable` amounts participate as known zero and never enter `missing`.

- [ ] **Step 5: Run engine + existing profitability regressions**

Run:

```bash
cd backend
pytest -q tests/test_dropshipping_unit_economics.py tests/test_product_analytics_v2.py tests/test_dropshipping_decision_intelligence.py
```

Expected: all PASS; existing gross-profit semantics unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dropshipping_unit_economics.py backend/tests/test_dropshipping_unit_economics.py
git commit -m "feat: calculate store contribution economics"
```

---

### Task 6: Expose Unit Economics analytics through the existing dropshipping API

**Files:**
- Modify: `backend/app/api/dropshipping_analytics.py`
- Test: `backend/tests/test_dropshipping_unit_economics_api.py`

**Interfaces:**
- API: `GET /api/stores/{store_id}/analytics/dropshipping/unit-economics`.
- Permissions: `analytics.read`.
- Store semantics: active, owned store only, matching current dropshipping endpoints.

- [ ] **Step 1: Write API RED tests**

Cover:
- 200 empty period with provenance/data-quality shape;
- date-only inclusive end reuses `_parse_range` contract;
- foreign store 404;
- inactive store 404;
- missing permission 403;
- Meta/config incompleteness still returns 200, not 5xx;
- provider error is represented as component state, not an endpoint failure.

- [ ] **Step 2: Confirm RED**

Run: `cd backend && pytest -q tests/test_dropshipping_unit_economics_api.py`

- [ ] **Step 3: Add thin endpoint**

```python
@router.get("/api/stores/{store_id}/analytics/dropshipping/unit-economics")
def dropshipping_unit_economics(...):
    store = _validate_store(store_id, membership, db)
    parsed_from, parsed_to = _parse_range(date_from, date_to)
    return get_store_unit_economics(
        db,
        membership.organization_id,
        store,
        parsed_from,
        parsed_to,
    )
```

- [ ] **Step 4: Run API tests**

Run: `cd backend && pytest -q tests/test_dropshipping_unit_economics_api.py tests/test_dropshipping_decision_intelligence_api.py`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/dropshipping_analytics.py backend/tests/test_dropshipping_unit_economics_api.py
git commit -m "feat: expose unit economics analytics"
```

---

### Task 7: Add the per-store Settings editor

**Files:**
- Create: `frontend/src/services/unitEconomics.ts`
- Create: `frontend/src/components/UnitEconomicsSettingsPanel.tsx`
- Modify: `frontend/src/pages/StoresPage.tsx`
- Create/Modify focused CSS according to existing store styles
- Test: `frontend/tests/unitEconomics.test.ts`

**Interfaces:**
- GET/PUT config client matching Task 2.
- Component props:

```ts
interface UnitEconomicsSettingsPanelProps {
  storeId: number;
  currency: string;
  canWrite: boolean;
}
```

- [ ] **Step 1: Write frontend RED tests for DTO normalization/presentation helpers**

Because the frontend test stack uses `node:test` rather than a DOM renderer, keep business/presentation logic in testable pure functions. Cover:
- percentage validation 0..100;
- monetary validation >=0;
- normalized duplicate methods are rejected before submit;
- fixed amount labels include store currency;
- `is_cod=false` hides/ignores method COD percentage in serialized payload.

- [ ] **Step 2: Confirm RED**

Run: `cd frontend && npm test -- --test-name-pattern="unit economics"`

If node's test-name forwarding is not supported by the installed version, run `npm test` and inspect only the new test file failures.

- [ ] **Step 3: Add typed client**

Define:

```ts
export interface UnitEconomicsPaymentMethodRule {
  payment_method: string;
  fee_percent: number | null;
  fee_fixed: number | null;
  is_cod: boolean;
  cod_fee_percent: number | null;
}

export interface UnitEconomicsConfig {
  store_id: number;
  currency: string;
  outbound_shipping_cost: number | null;
  return_logistics_cost: number | null;
  default_payment_fee_percent: number | null;
  default_payment_fee_fixed: number | null;
  default_cod_fee_percent: number | null;
  payment_methods: UnitEconomicsPaymentMethodRule[];
}
```

Add `getUnitEconomicsConfig(storeId)` and `replaceUnitEconomicsConfig(storeId, payload)` using the same global-scope header convention as `stores.ts`.

- [ ] **Step 4: Build isolated settings component**

UI fields:
- outbound shipping fixed cost;
- return logistics fixed cost;
- default payment `%` and fixed fee;
- default COD `%`;
- repeatable payment-method overrides with method key, `%`, fixed fee, `is_cod`, optional COD `%`.

Show `Actual / Estimated` language only where useful; this screen edits assumptions, so label configured values explicitly as estimates. Never imply Meta can be manually configured.

- [ ] **Step 5: Integrate into existing-store configuration flow**

Render the panel only for an existing `editingStore`; new-store creation remains unchanged. A store must exist before Unit Economics config can be saved.

On currency change, after successful store save, show a localized notice that fixed monetary assumptions were cleared and must be reconfigured.

- [ ] **Step 6: Verify frontend tests/build**

Run:

```bash
cd frontend
npm test
npm run build
npm run lint
```

Expected: tests/build pass; lint has no new errors and no new warnings attributable to V2.2.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/services/unitEconomics.ts frontend/src/components/UnitEconomicsSettingsPanel.tsx frontend/src/pages/StoresPage.tsx frontend/tests/unitEconomics.test.ts frontend/src/*.css
git commit -m "feat: configure store unit economics"
```

---

### Task 8: Add the Unit Economics analytics presentation and failure isolation

**Files:**
- Modify: `frontend/src/services/analytics.ts`
- Create: `frontend/src/components/DropshippingUnitEconomics.tsx`
- Create: `frontend/src/utils/unitEconomics.ts`
- Modify: `frontend/src/components/DropshippingOverview.tsx`
- Modify: `frontend/src/utils/dropshippingAnalyticsState.ts`
- Modify: `frontend/tests/dropshippingAnalyticsState.test.ts`
- Modify: `frontend/tests/unitEconomics.test.ts`

**Interfaces:**
- New dashboard section key: `unitEconomics`.
- Analytics client: `getDropshippingUnitEconomics(storeId, dateFrom?, dateTo?)`.

- [ ] **Step 1: Extend resilience tests RED**

Update the expected section list from five to six:

```ts
assert.deepEqual(DROPSHIPPING_ANALYTICS_SECTIONS, [
  "overview",
  "profitability",
  "products",
  "orders",
  "insights",
  "unitEconomics",
]);
```

Add tests proving Unit Economics-only failure does not make the dashboard globally fail and all-six failure does.

- [ ] **Step 2: Add pure presentation-helper RED tests**

Cover:
- complete contribution displays amount and margin;
- incomplete contribution never formats `known_cost_subtotal` as contribution profit;
- `actual`, `estimated`, `missing`, `not_applicable` labels localize ES/EN/PT-BR;
- known missing reasons map to human-readable copy;
- unknown machine keys never leak raw to UI; helper returns safe fallback copy.

- [ ] **Step 3: Implement typed analytics DTO/client**

Use exact component type:

```ts
export type UnitEconomicsSource = "actual" | "estimated" | "missing" | "not_applicable";
export type UnitEconomicsStatus = "available" | "missing" | "not_applicable";

export interface UnitEconomicsCostComponent {
  amount: number | null;
  source: UnitEconomicsSource;
  status: UnitEconomicsStatus;
  reason: string | null;
  metadata: Record<string, unknown>;
}
```

Define response types for `components`, `data_quality`, `order_counts`, and contribution fields.

- [ ] **Step 4: Add sixth `Promise.allSettled` request**

Keep existing five requests in current order and append Unit Economics as result index 5. Add `unitEconomics` to `DashboardData`, failed-section labels, and state mapping.

- [ ] **Step 5: Build `DropshippingUnitEconomics` component**

Presentation requirements:
- title: localized equivalent of `Economía real`;
- show recognized revenue, COGS, gross profit, shipping, payment fees, COD fees, reverse logistics, Meta Ads, contribution profit, contribution margin;
- provenance badge on cost rows;
- when incomplete, contribution fields show `—`/`Incompleto`, never a partial number;
- show one concise missing-data explanation and `Configurar costos` shortcut for configurable missing components;
- Meta-specific missing reason directs user to Meta integration, not Settings;
- estimated values are visually distinguishable without alarm styling;
- no product-level ad allocation UI.

- [ ] **Step 6: Run frontend tests/build/lint**

Run:

```bash
cd frontend
npm test
npm run build
npm run lint
```

Expected: PASS except already-known pre-existing lint warnings; V2.2 introduces none.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/services/analytics.ts frontend/src/components/DropshippingUnitEconomics.tsx frontend/src/components/DropshippingOverview.tsx frontend/src/utils/unitEconomics.ts frontend/src/utils/dropshippingAnalyticsState.ts frontend/tests/unitEconomics.test.ts frontend/tests/dropshippingAnalyticsState.test.ts frontend/src/*.css
git commit -m "feat: show dropshipping contribution economics"
```

---

### Task 9: Restore strict route contract and perform full verification

**Files:**
- Modify: `backend/tests/contracts/api_routes.json`
- Modify: `backend/tests/test_route_contract.py` only if needed to remove the temporary V2.1 `INTENTIONAL_ADDITIVE_ROUTES` compatibility exception after regenerating the snapshot.
- No product code unless verification exposes a genuine defect.

**Interfaces:**
- The route snapshot must include:
  - `GET /api/stores/{store_id}/analytics/dropshipping/insights`
  - `GET /api/stores/{store_id}/analytics/dropshipping/unit-economics`
  - `GET /api/stores/{store_id}/unit-economics/config`
  - `PUT /api/stores/{store_id}/unit-economics/config`

- [ ] **Step 1: Run route-contract test and confirm expected additive failure before snapshot regeneration**

Run: `cd backend && pytest -q tests/test_route_contract.py`

- [ ] **Step 2: Regenerate the route snapshot using the repository's existing route snapshot mechanism**

Do not add another permanent allowlist. Once regenerated, remove `INTENTIONAL_ADDITIVE_ROUTES` if the snapshot now directly contains V2.1 and V2.2 routes.

- [ ] **Step 3: Run targeted backend suite**

```bash
cd backend
pytest -q \
  tests/test_unit_economics_models.py \
  tests/test_unit_economics_config_service.py \
  tests/test_unit_economics_config_api.py \
  tests/test_unit_economics_meta.py \
  tests/test_dropshipping_unit_economics.py \
  tests/test_dropshipping_unit_economics_api.py \
  tests/test_dropshipping_decision_intelligence.py \
  tests/test_dropshipping_decision_intelligence_api.py \
  tests/test_product_analytics_v2.py \
  tests/test_route_contract.py
```

Expected: all PASS.

- [ ] **Step 4: Run full backend verification**

```bash
cd backend
ruff check .
pytest -q
```

Expected: zero lint errors, zero test failures.

- [ ] **Step 5: Run full frontend verification**

```bash
cd frontend
npm test
npm run lint
npm run build
```

Expected: tests/build PASS; no new lint errors/warnings. Existing warnings must be explicitly reported, not silently attributed to V2.2.

- [ ] **Step 6: Verify migration head**

```bash
cd backend
alembic heads
```

Expected: exactly `n0b1c2d3e4f5 (head)`.

- [ ] **Step 7: Commit verification/contract update**

```bash
git add backend/tests/contracts/api_routes.json backend/tests/test_route_contract.py
git commit -m "test: lock unit economics route contract"
```

- [ ] **Step 8: Compare branch to base before PR**

Verify no unrelated files changed, no secrets were committed, and the branch remains based on the approved V2.2 spec. Then open a PR only after fresh green CI.

---

## Plan Self-Review

### Spec coverage
- Real-first/configured fallback: Tasks 2, 4, 5.
- Provenance/completeness: Tasks 4, 5, 8.
- Store-level Meta only/no allocation: Tasks 4, 5, 8.
- Store defaults + payment overrides: Tasks 1, 2, 5, 7.
- Return/cancel lifecycle semantics: Task 5.
- Currency mismatch/no FX: Tasks 3, 4.
- Meta disconnected => incomplete: Tasks 4, 5, 8.
- Settings single edit source: Task 7.
- Existing gross-profit semantics preserved: Tasks 5 and 9 regression suite.
- Multi-tenant isolation/permissions: Tasks 2 and 6.
- Dashboard partial failure isolation: Task 8.
- Migration/strict route contract: Tasks 1 and 9.

### Type consistency
- Backend component shape is constant across Meta resolver, engine, API, and frontend DTO.
- `unitEconomics` is the single frontend section key everywhere.
- Configuration method keys use `strip().casefold()` on backend; frontend validation mirrors but does not replace server enforcement.
- Fixed monetary assumptions have no separate stored currency and are cleared on Store currency change.

### Scope control
- No product-level contribution margin.
- No campaign attribution.
- No FX.
- No manual advertising fallback.
- No taxes/overhead/general ledger.
- No changes to Decision Intelligence rules in V2.2.
