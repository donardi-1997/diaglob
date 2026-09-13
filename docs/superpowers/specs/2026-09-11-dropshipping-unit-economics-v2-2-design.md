# Dropshipping Analytics V2.2 — Unit Economics Design

Date: 2026-09-11
Status: Design approved; written spec pending user review
Scope: Diaglob dropshipping analytics, store configuration, Meta Ads cost ingestion

## 1. Purpose

Dropshipping Analytics V2.2 adds store-level unit economics on top of the existing delivered-order gross-profit analytics.

The feature answers:

> After product cost and operating costs that Diaglob can either observe or explicitly estimate, how much contribution profit did this store generate for the selected period?

The design prioritizes accounting honesty over apparent completeness. Diaglob must never silently replace an unknown applicable cost with zero or present an incomplete contribution margin as final profitability.

## 2. Fixed product decisions

1. Cost resolution is **real-first with configurable estimated fallbacks**.
2. Every cost component reports provenance as `actual`, `estimated`, `missing`, or `not_applicable`.
3. Advertising spend is calculated **only at store level**. V2.2 does not allocate ad spend to products.
4. Cost assumptions are configured **per store**, with store defaults and optional payment-method overrides.
5. Returned orders are treated as an operating loss, not completed revenue.
6. Cancelled orders have zero recognized revenue and no invented shipping, COGS, or payment costs.
7. Meta Ads spend is accepted only when Meta account currency exactly matches store currency.
8. No FX conversion is performed in V2.2.
9. If Meta Ads is disconnected, unavailable, lacks a usable bounded period, or uses another/unknown currency, advertising spend is `missing` and final contribution metrics are incomplete.
10. Settings are the single source of truth for estimated operating costs. Analytics may link to Settings but does not duplicate editable configuration.
11. Existing gross-profit semantics remain unchanged.

## 3. Non-goals

V2.2 does not:

- allocate ads to products, SKUs, campaigns, customers, or orders;
- implement campaign-to-product attribution;
- convert currencies;
- estimate ad spend without Meta;
- model taxes, payroll, SaaS subscriptions, warehouse rent, financing, or corporate overhead;
- model damaged/non-recoverable returned inventory;
- change Product Analytics V2 gross-profit calculations;
- change Decision Intelligence V2.1 rules;
- provide accrual accounting or audited financial statements.

This is an operating contribution view for dropshipping decisions, not a general ledger.

## 4. Existing semantics remain authoritative

The current dropshipping analytics service defines delivered revenue and gross profit from orders whose current `lifecycle_status` is `delivered`. COGS is derived from `OrderItem.unit_cost * quantity`.

V2.2 reuses those lifecycle and cohort semantics instead of creating a second definition of revenue.

The order cohort continues to use the existing analytics date semantics on `Order.created_at`. Because lifecycle status is current state, historical periods may change when an order later becomes delivered, returned, or cancelled. This matches the current dashboard.

Meta Ads spend is calendar spend for the selected bounded date range. The contribution result is therefore a blended store operating view aligned to the selected analytics window, not order-level attribution.

## 5. Financial model

### 5.1 Recognized revenue

`recognized_revenue` is the sum of `Order.total_amount` for cohort orders whose current lifecycle status is `delivered`.

- delivered: revenue recognized
- returned: revenue = 0
- cancelled: revenue = 0
- confirmed/shipped/unknown: excluded from recognized contribution revenue

### 5.2 COGS

COGS is `OrderItem.unit_cost * quantity` for delivered orders only.

Returned orders contribute zero COGS because V2.2 assumes returned inventory is recoverable. Non-recoverable inventory loss is out of scope.

If any delivered item lacks `unit_cost`, COGS is `missing` for final-contribution purposes. The service may expose known COGS subtotal and completeness percentage, but final contribution metrics are withheld.

If there are no delivered items, COGS is zero and `not_applicable`; it does not make the period incomplete.

### 5.3 Outbound shipping

Outbound shipping applies to terminal fulfilled outcomes:

- delivered: yes
- returned: yes
- cancelled: no
- confirmed/shipped/unknown: no recognized outbound shipping in V2.2

V2.2 has no persisted order-level actual shipping-cost field, so shipping is normally `estimated` from store configuration.

If at least one delivered/returned order exists and no estimate is configured, outbound shipping is `missing`. If no delivered/returned orders exist, the component is zero and `not_applicable` even when no estimate exists.

A future explicit actual shipping source may take precedence without changing the public contract.

### 5.4 Reverse logistics

Each returned order may receive a configured fixed reverse-logistics cost.

- returned orders + configured cost: `estimated`
- returned orders + no configured cost: `missing`, reason `return_cost_missing`
- no returned orders: amount 0, `not_applicable`

Return logistics is separate from outbound shipping. A returned order may contribute both.

### 5.5 Payment gateway fees

For delivered orders, payment fees are resolved using normalized `Order.payment_method`.

Estimated formula:

`fee = order.total_amount * fee_percent / 100 + fee_fixed`

Resolution priority:

1. explicit actual provider fee in store currency, if such a source exists;
2. matching payment-method override;
3. store default payment fee;
4. `missing`.

Overrides are field-level. An unset override percentage/fixed field falls back to the corresponding store default.

Current `PaymentTransaction` records contain amount/status/method but no provider fee, so transaction amount must never be interpreted as a fee.

If delivered orders exist and one or more cannot resolve a payment fee, the aggregate payment-fee component is `missing`. The response should expose unresolved normalized methods in component metadata, using a stable sentinel such as `__missing__` when `Order.payment_method` is null/blank.

If there are no delivered orders, payment fees are zero and `not_applicable`.

For returned orders, V2.2 does not apply an estimated payment fee. A returned-order fee is counted only if a future/available source explicitly proves a non-refunded retained fee. Without such proof it remains zero under the approved return policy.

Cancelled orders receive no payment fee.

### 5.6 COD fees

COD is configured as a payment-method property, not guessed from arbitrary strings in analytics code.

A payment-method rule contains `is_cod`. For a delivered order whose matched rule has `is_cod=true`:

`cod_fee = order.total_amount * cod_fee_percent / 100`

Resolution priority:

1. method-specific `cod_fee_percent`;
2. store default `default_cod_fee_percent`;
3. `missing`, reason `cod_fee_rule_missing`.

If no delivered COD orders exist, COD fees are zero and `not_applicable`.

Returned and cancelled orders do not receive estimated COD fees.

### 5.7 Meta Ads spend

Meta Ads is the only advertising source in V2.2.

For a bounded selected range, the service uses the existing account-level Meta Ads `get_insights(..., time_range=...)` and reads spend.

Meta spend is `actual` only when:

- the store has a connected Meta Ads account;
- the analytics range is bounded and can be represented as Meta `time_range`;
- provider request succeeds;
- Meta account currency is known;
- normalized Meta currency equals normalized store currency.

A successful Meta request with no spend is **actual zero**, not missing.

Missing reasons:

- `meta_not_connected`
- `bounded_date_range_required`
- `currency_unknown`
- `currency_mismatch`
- `provider_error`
- `credentials_unavailable`

No manual/configured advertising fallback exists.

The date adapter must preserve the analytics half-open interval `[date_from, date_to_exclusive)` while translating correctly to Meta calendar `since`/`until`, avoiding off-by-one days.

### 5.8 Contribution profit and margin

When every applicable mandatory component is available:

`contribution_profit = recognized_revenue - cogs - outbound_shipping - payment_fees - cod_fees - reverse_logistics - ad_spend`

`contribution_margin = contribution_profit / recognized_revenue * 100`

If recognized revenue is zero, contribution margin is `null` even when data quality is complete. Contribution profit may be negative when a complete period contains costs such as ads/returns but no delivered revenue.

If any applicable mandatory component is missing:

- `contribution_profit = null`
- `contribution_margin = null`
- top-level status = `incomplete`

The response may expose `known_cost_subtotal`, but the UI must never label it as contribution profit.

## 6. Completeness and provenance

Every component returns at least:

```json
{
  "amount": 15000.0,
  "source": "estimated",
  "status": "available",
  "reason": null,
  "metadata": {}
}
```

Allowed `source` values:

- `actual`
- `estimated`
- `missing`
- `not_applicable`

Allowed `status` values:

- `available`
- `missing`
- `not_applicable`

Top-level `data_quality` includes:

- `status`: `complete` or `incomplete`
- `missing_components`
- `missing_reasons`
- `estimated_components`
- `actual_components`

`not_applicable` components do not make a result incomplete.

A numeric zero never proves availability. Availability comes from resolver state.

Stable component missing reasons include at least:

- `cogs_incomplete`
- `shipping_estimate_missing`
- `payment_fee_rule_missing`
- `cod_fee_rule_missing`
- `return_cost_missing`
- Meta reasons from section 5.7

Component `metadata` may expose non-sensitive diagnostic fields required by the UI, including:

- `cost_completeness_pct`
- `unresolved_payment_methods`
- `provider_currency`
- `store_currency`

## 7. Persistence

### 7.1 `StoreUnitEconomicsConfig`

Use a dedicated model/table rather than financial-policy columns on `Store`.

Fields:

- `id`
- `organization_id` — required, indexed, FK organizations
- `store_id` — required, unique, indexed, FK stores
- `outbound_shipping_cost` — nullable numeric(18,4)
- `return_logistics_cost` — nullable numeric(18,4)
- `default_payment_fee_percent` — nullable decimal percentage
- `default_payment_fee_fixed` — nullable numeric(18,4)
- `default_cod_fee_percent` — nullable decimal percentage
- `created_at`
- `updated_at`

All fixed monetary values are denominated in current store currency. No second mutable currency field is stored.

Validation:

- monetary values >= 0
- percentages 0..100
- ownership by organization/store
- at most one config per store

### 7.2 `PaymentMethodCostRule`

Child table for method overrides.

Fields:

- `id`
- `organization_id`
- `store_id`
- `unit_economics_config_id`
- `payment_method` — normalized key, length compatible with `Order.payment_method`
- `fee_percent` — nullable
- `fee_fixed` — nullable
- `is_cod` — boolean, default false
- `cod_fee_percent` — nullable
- `created_at`
- `updated_at`

Constraints:

- unique `(store_id, payment_method)`
- monetary values >= 0
- percentages 0..100
- rule organization/store must match parent config

Normalization is `strip().casefold()` at the service boundary. Empty normalized methods are rejected. Duplicate methods after normalization are rejected before persistence.

### 7.3 Store currency changes

Changing `Store.currency` must never silently reinterpret fixed monetary assumptions.

V2.2 uses this behavior:

- currency change remains allowed;
- transactionally clear fixed monetary assumptions:
  - `outbound_shipping_cost`
  - `return_logistics_cost`
  - `default_payment_fee_fixed`
  - method-level `fee_fixed`
- percentage assumptions may remain;
- no FX conversion is performed;
- UI tells the user that fixed Unit Economics assumptions must be reconfigured.

## 8. Service architecture

Business logic remains in `backend/app/services/`.

### `unit_economics_config_service`

Responsibilities:

- read/upsert config;
- validate ranges;
- normalize payment methods;
- enforce organization/store ownership;
- transactionally replace overrides;
- clear fixed monetary estimates on store currency change;
- return stable DTOs.

### `dropshipping_unit_economics`

Responsibilities:

- load exact order cohort;
- reuse current delivered revenue/COGS semantics where practical;
- compute lifecycle-sensitive operating costs;
- resolve defaults/overrides;
- resolve Meta spend;
- produce provenance and completeness metadata;
- never mutate orders/products/payments.

### Meta spend helper

Provider HTTP remains in the existing Meta Ads client. Add only service-level orchestration for exact-period spend, currency validation, provider failure normalization, and provenance.

## 9. API contracts

### 9.1 GET config

`GET /api/stores/{store_id}/unit-economics/config`

Permission: `stores.read`.

Behavior:

- validates organization ownership and `Store.deleted == false`;
- may read active or suspended stores, matching store-management semantics;
- returns stable empty/default DTO when no config exists without creating a row;
- includes current store currency;
- includes normalized method rules.

### 9.2 PUT config

`PUT /api/stores/{store_id}/unit-economics/config`

Permission: `stores.write`.

Behavior:

- full replacement/upsert of defaults and method rules;
- transactionally replaces stale overrides;
- validates organization ownership and non-deleted store;
- validates values;
- rejects duplicate normalized methods;
- frontend cannot override organization/store identity;
- any currency field in the DTO, if exposed for display, is read-only and must match the store currency.

Full-replacement PUT is preferred to piecemeal PATCH because the object is small and it prevents stale overrides from surviving unintentionally.

### 9.3 GET analytics

`GET /api/stores/{store_id}/analytics/dropshipping/unit-economics?date_from=...&date_to=...`

Permission: `analytics.read`.

Store validation and date parsing follow existing dropshipping analytics behavior, including active-store semantics.

Illustrative response:

```json
{
  "store_id": 1,
  "currency": "COP",
  "date_from": "2026-09-01",
  "date_to": "2026-09-11",
  "recognized_revenue": 2500000.0,
  "gross_profit": 900000.0,
  "components": {
    "cogs": {
      "amount": 1600000.0,
      "source": "actual",
      "status": "available",
      "reason": null,
      "metadata": {"cost_completeness_pct": 100.0}
    },
    "outbound_shipping": {
      "amount": 180000.0,
      "source": "estimated",
      "status": "available",
      "reason": null,
      "metadata": {}
    },
    "payment_fees": {
      "amount": 92000.0,
      "source": "estimated",
      "status": "available",
      "reason": null,
      "metadata": {"unresolved_payment_methods": []}
    },
    "cod_fees": {
      "amount": 21000.0,
      "source": "estimated",
      "status": "available",
      "reason": null,
      "metadata": {}
    },
    "reverse_logistics": {
      "amount": 36000.0,
      "source": "estimated",
      "status": "available",
      "reason": null,
      "metadata": {}
    },
    "ad_spend": {
      "amount": null,
      "source": "missing",
      "status": "missing",
      "reason": "meta_not_connected",
      "metadata": {"provider_currency": null, "store_currency": "COP"}
    }
  },
  "known_cost_subtotal": 1929000.0,
  "contribution_profit": null,
  "contribution_margin": null,
  "data_quality": {
    "status": "incomplete",
    "missing_components": ["ad_spend"],
    "missing_reasons": ["meta_not_connected"],
    "estimated_components": [
      "outbound_shipping",
      "payment_fees",
      "cod_fees",
      "reverse_logistics"
    ],
    "actual_components": ["cogs"]
  },
  "order_counts": {
    "delivered": 12,
    "returned": 2,
    "cancelled": 3,
    "open_or_unknown_excluded": 4
  }
}
```

Serialization follows established repository conventions. Tests must prevent NaN/Infinity and ambiguous zero-as-missing behavior.

## 10. Frontend configuration UX

Settings are the only editable source of assumptions.

Use the existing store-configuration experience as the store-specific Settings surface and add a **Unit Economics** section rather than creating an editable Analytics form.

Fields:

- average outbound shipping cost
- average reverse-logistics cost
- default payment fee percentage
- default payment fixed fee
- default COD fee percentage
- payment-method overrides:
  - normalized/display method
  - payment fee %
  - fixed fee
  - COD toggle
  - COD fee %

Requirements:

- show store currency beside fixed monetary fields;
- state clearly that configured values are estimates;
- inline validation;
- removing a value returns an applicable component to `missing` if no actual source exists;
- overrides can be deleted;
- ES, EN, PT-BR localization;
- edit requires `stores.write`;
- currency-change flow warns that fixed monetary assumptions were cleared.

## 11. Analytics UX

Add an **Economía real / Unit Economics / Economia unitária** section near delivered profitability.

Display:

- recognized revenue
- COGS
- gross profit
- outbound shipping
- payment fees
- COD fees
- reverse logistics
- Meta Ads spend
- contribution profit
- contribution margin

Each cost row exposes a source badge:

- Actual
- Estimado
- Falta dato
- No aplica, where useful

Complete result: emphasize contribution profit and margin.

Incomplete result:

- show `Contribution Margin — Incomplete` rather than a percentage;
- render final contribution values as `—`, backed by API `null`;
- show missing components/reasons;
- keep known costs visible;
- show context-specific CTA: `Configure costs` and/or `Connect Meta Ads`;
- `Configure costs` navigates to the selected store's Unit Economics Settings section.

For Meta currency mismatch, show both provider and store currency from component metadata.

## 12. Dashboard resilience

The dashboard already isolates requests with `Promise.allSettled`.

Unit Economics becomes one additional independent section.

Requirements:

- its request failure must not hide overview, profitability, products, orders, or Decision Intelligence;
- partial-unavailable messaging includes Unit Economics on request failure;
- an HTTP 200 incomplete financial result renders normally with data-quality warnings and is not considered unavailable;
- only transport/server/request failures mark the section unavailable.

## 13. Security and tenancy

Every config and analytics query is constrained by both `organization_id` and `store_id`.

Foreign/deleted/inaccessible stores expose no configuration or financial data.

Permissions:

- config read: `stores.read`
- config write: `stores.write`
- analytics: `analytics.read`

Never trust organization id, store ownership, or currency supplied by the frontend.

## 14. Error handling

### Configuration

- negative amount: 422
- percentage outside 0..100: 422
- duplicate normalized method: 422
- inaccessible store: repository-consistent 404
- insufficient permission: 403

### Analytics

Meta/provider failures are data-quality conditions when commerce analytics can still be computed:

- timeout/provider error -> HTTP 200, `ad_spend missing/provider_error`
- Meta disconnected -> HTTP 200, `meta_not_connected`
- currency unknown/mismatch -> HTTP 200 incomplete response

Database/core service failures may fail the endpoint normally.

Do not leak tokens, encrypted secrets, or raw authentication payloads in errors/logs.

## 15. Testing strategy

Implementation follows TDD.

### Model/migration

Verify:

- one config per store;
- ownership constraints/service enforcement;
- numeric validation;
- cascade/delete behavior;
- migration upgrade on supported DB path.

### Config service/API

Verify:

- empty GET without side-effect row creation;
- full upsert/replacement;
- clearing nullable estimates;
- defaults + overrides serialization;
- duplicate normalized methods rejected;
- foreign/deleted store behavior;
- permission gates;
- suspended store config access consistent with store management;
- currency change transactionally clears all fixed monetary estimates but preserves percentages.

### Unit economics service

At minimum:

1. fully complete result with estimated operating costs + actual Meta spend;
2. incomplete COGS withholds final contribution;
3. no delivered items -> COGS/payment fees not applicable;
4. applicable shipping missing -> incomplete;
5. no returned orders -> reverse logistics not applicable;
6. returned order -> revenue/COGS zero + outbound/reverse logistics;
7. cancelled order -> zero direct operating costs;
8. confirmed/shipped/unknown excluded from recognized direct contribution;
9. payment method override beats defaults;
10. partial method override falls back field-by-field;
11. unresolved delivered payment method with no default -> incomplete;
12. COD only for configured COD methods;
13. no delivered COD orders -> COD not applicable;
14. no COD estimate for returned/cancelled;
15. Meta disconnected -> incomplete;
16. Meta currency unknown -> incomplete;
17. Meta currency mismatch -> incomplete and exposes both currencies;
18. Meta provider failure -> 200-compatible missing component;
19. successful Meta zero spend -> actual zero;
20. bounded range translated without off-by-one;
21. unbounded/single-ended range -> ad spend missing `bounded_date_range_required`;
22. zero recognized revenue -> margin null, no NaN/Infinity;
23. strict tenant/store isolation.

### Frontend

Verify:

- ES/EN/PT-BR labels;
- source badges including not-applicable state;
- complete contribution display;
- incomplete response never displays fabricated contribution metrics;
- missing config/Meta CTAs;
- currency mismatch text;
- Settings validation/overrides;
- currency-change warning;
- Unit Economics request failure leaves other dashboard sections healthy;
- incomplete HTTP 200 renders as data, not unavailable.

### Regression

Existing dropshipping overview, profitability, Product Analytics V2, Decision Intelligence V2.1, Meta analytics, store configuration, permissions, and route-contract tests remain green.

## 16. Observability

Structured logs may include:

- organization/store ids
- date range
- Meta availability reason
- Meta/store currency on mismatch
- completeness status
- missing component names

Never log tokens, encrypted secrets, customer payment details, or raw auth payloads.

## 17. Rollout and compatibility

Migration creates nullable configuration. Existing stores start with no operating-cost assumptions.

After deployment:

- existing gross-profit analytics continue unchanged;
- Unit Economics may initially be incomplete;
- users explicitly configure shipping/payment/return assumptions;
- Meta must be connected to complete ad spend;
- no historical backfill is required;
- no synthetic default costs are seeded.

This prevents silent profitability changes for existing tenants.

## 18. Acceptance criteria

V2.2 is complete when:

1. each store can persist defaults and payment-method overrides;
2. fixed monetary assumptions are never silently reinterpreted after currency change;
3. analytics implements the approved lifecycle cost model;
4. Meta spend is fetched only for exact bounded periods and accepted only in matching known currency;
5. each component exposes actual/estimated/missing/not-applicable provenance;
6. missing applicable components withhold final contribution profit and margin;
7. successful zero results are distinguishable from missing data;
8. returned/cancelled orders obey approved rules;
9. Settings is the only editable assumption source;
10. Analytics links to Settings/Meta when action is required;
11. Unit Economics request failures are isolated from the rest of the dashboard;
12. tenant isolation and permissions are enforced;
13. ES, EN, PT-BR presentation is supported;
14. targeted and full regression suites pass.
