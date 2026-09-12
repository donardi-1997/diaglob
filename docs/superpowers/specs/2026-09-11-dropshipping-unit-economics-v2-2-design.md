# Dropshipping Analytics V2.2 — Unit Economics Design

Date: 2026-09-11
Status: Approved design
Scope: Diaglob dropshipping analytics, store configuration, Meta Ads cost ingestion

## 1. Purpose

Dropshipping Analytics V2.2 adds store-level unit economics on top of the existing delivered-order gross-profit analytics.

The feature must answer a narrower financial question than the existing dashboard:

> After product cost and the operating costs that Diaglob can either observe or explicitly estimate, how much contribution profit did this store generate for the selected period?

The design prioritizes accounting honesty over apparent completeness. Diaglob must never silently replace an unknown cost with zero or present an incomplete contribution margin as final profitability.

## 2. Product decisions

The following decisions are fixed for V2.2:

1. Cost resolution is **real-first with configurable estimated fallbacks**.
2. Every cost component reports its provenance as `actual`, `estimated`, or `missing`.
3. Advertising spend is calculated **only at store level**. V2.2 does not allocate ad spend to products.
4. Cost assumptions are configured **per store**, with store defaults and optional payment-method overrides.
5. Returned orders are treated as an operating loss, not as completed revenue.
6. Cancelled orders have zero recognized revenue and no invented shipping, COGS, or payment costs.
7. Meta Ads spend is used only when the Meta account currency exactly matches the store currency.
8. No FX conversion is performed in V2.2.
9. When Meta Ads is disconnected, unavailable, unbounded by a usable date range, or in another currency, advertising spend is `missing` and final contribution metrics are incomplete.
10. Settings are the single source of truth for estimated operating costs. Analytics contains a shortcut to configure them but does not duplicate editable configuration.
11. Existing gross-profit semantics remain unchanged.

## 3. Non-goals

V2.2 does not:

- allocate advertising spend to products, SKUs, campaigns, customers, or individual orders;
- implement campaign-to-product attribution;
- convert currencies;
- estimate ad spend when Meta Ads is unavailable;
- model taxes, payroll, SaaS subscriptions, warehouse rent, financing, or corporate overhead;
- model damaged/non-recoverable returned inventory;
- change existing Product Analytics V2 gross-profit calculations;
- change existing Decision Intelligence V2.1 rules unless a later task explicitly consumes Unit Economics outputs;
- provide accrual-accounting or audited financial statements.

The feature is an operating contribution view for dropshipping decisions, not a general ledger.

## 4. Existing semantics that remain authoritative

The current dropshipping analytics service defines delivered revenue and gross profit from orders whose current `lifecycle_status` is `delivered`. COGS is derived from `OrderItem.unit_cost * quantity`.

V2.2 reuses those lifecycle and cohort semantics instead of creating a second definition of delivered revenue.

The selected order cohort continues to be filtered using the existing analytics date semantics on `Order.created_at`. Because lifecycle status is current state, historical periods may change when an order later moves from shipped to delivered, returned, or cancelled. This is already true of the existing dashboard and remains intentional in V2.2.

Meta Ads spend is calendar spend for the selected bounded date range. Therefore the store-level contribution result is a blended operating view aligned to the selected analytics window; it is not an order-level attribution model.

## 5. Financial model

### 5.1 Recognized revenue

`recognized_revenue` is the sum of `Order.total_amount` for orders in the selected cohort whose current lifecycle status is `delivered`.

- delivered: revenue recognized
- returned: revenue = 0
- cancelled: revenue = 0
- confirmed/shipped/unknown: revenue is not recognized in contribution profit

### 5.2 COGS

COGS is the sum of `OrderItem.unit_cost * quantity` for delivered orders only.

Returned orders contribute zero COGS in V2.2 because the approved model assumes returned inventory is recoverable. Non-recoverable inventory loss is out of scope.

If any delivered item lacks `unit_cost`, the COGS component is incomplete. The service may expose the known COGS subtotal and completeness percentage for diagnosis, but final `contribution_profit` and `contribution_margin` must be `null` until COGS is complete.

### 5.3 Outbound shipping

Outbound shipping applies to terminal fulfilled outcomes:

- delivered: yes
- returned: yes
- cancelled: no
- confirmed/shipped/unknown: no recognized outbound shipping in V2.2

V2.2 currently has no persisted order-level actual shipping-cost field. Therefore shipping is normally `estimated` from the store configuration. If no configured estimate exists, the component is `missing`.

The resolver must be structured so a future real shipping source can take precedence without changing the public analytics contract.

### 5.4 Reverse logistics / return cost

Each returned order may receive a configured fixed reverse-logistics cost.

- source in V2.2: `estimated` when configured
- source: `missing` when returned orders exist and no return-cost estimate is configured
- amount: zero with a non-missing status when there are no returned orders in the selected cohort

The return-cost estimate is separate from outbound shipping. A returned order may therefore contribute both the outbound shipping estimate and the reverse-logistics estimate.

### 5.5 Payment gateway fees

For delivered orders, payment fees are resolved from the order's normalized `payment_method`.

Estimated fee formula:

`fee = order.total_amount * fee_percent / 100 + fee_fixed`

Resolution priority for delivered orders:

1. future compatible actual fee source, when an explicit provider fee exists and is in store currency;
2. matching payment-method override;
3. store default payment fee;
4. `missing`.

An override may replace either or both percentage and fixed portions. Any unset override field falls back to the corresponding store default field.

Current `PaymentTransaction` records contain amount/status/method but do not contain an actual provider fee, so V2.2 must not infer an actual fee from transaction amount.

For returned orders, V2.2 does not apply an estimated payment fee. A returned-order payment fee is counted only if a future/available source explicitly proves that a non-refunded fee was retained. Absence of such proof is treated as zero under the approved return policy, not as an invented estimated cost.

Cancelled orders receive no payment fee by default.

### 5.6 COD fees

COD is modeled as a payment-method property, not by guessing from arbitrary strings at analytics time.

A payment-method cost rule contains `is_cod`. When `is_cod` is true for a delivered order, the COD fee is:

`cod_fee = order.total_amount * cod_fee_percent / 100`

Resolution priority:

1. method-specific `cod_fee_percent`;
2. store default `cod_fee_percent`;
3. `missing` when a delivered COD order exists and neither is configured.

Non-COD methods contribute zero COD fee with a known/not-applicable status.

Returned and cancelled orders do not receive estimated COD fees because payment collection is not considered proven by lifecycle state alone.

### 5.7 Meta Ads spend

Meta Ads is the only advertising source in V2.2.

For a bounded selected date range, the service uses the existing Meta Ads client `get_insights(..., time_range=...)` at account level and reads `spend`.

Meta spend is `actual` only when all of these are true:

- the store has a connected Meta Ads account;
- the selected analytics range can be represented as a bounded Meta `time_range`;
- the provider request succeeds;
- `MetaAdsConnection.account_currency == Store.currency` after normalization.

A successful provider response with no spend is an **actual zero**, not missing data.

Meta spend is `missing` with an explicit reason when any of these apply:

- `meta_not_connected`
- `bounded_date_range_required`
- `currency_mismatch`
- `provider_error`
- `credentials_unavailable`

No configured/manual fallback exists for ad spend in V2.2.

The date-range adapter must preserve the existing analytics half-open interval `[date_from, date_to_exclusive)` while translating it correctly to Meta's calendar-date `since`/`until` contract, avoiding an off-by-one day.

### 5.8 Contribution profit and margin

When all mandatory components are known:

`contribution_profit = recognized_revenue - cogs - outbound_shipping - payment_fees - cod_fees - reverse_logistics - ad_spend`

`contribution_margin = contribution_profit / recognized_revenue * 100`

If recognized revenue is zero, contribution margin is `null` even when costs are complete. Contribution profit may still be negative when a complete period contains costs but no delivered revenue.

If any mandatory component is missing, both final contribution metrics are withheld:

- `contribution_profit = null`
- `contribution_margin = null`
- `status = incomplete`

The response may include `known_cost_subtotal` and all known component amounts for transparency, but the UI must not relabel that subtotal as contribution profit.

## 6. Completeness model

Each component returns at least:

```json
{
  "amount": 15000.0,
  "source": "estimated",
  "status": "available",
  "reason": null
}
```

Allowed `source` values:

- `actual`
- `estimated`
- `missing`
- `not_applicable`

Allowed component `status` values:

- `available`
- `missing`
- `not_applicable`

The top-level data-quality object contains:

- `status`: `complete` or `incomplete`
- `missing_components`: stable machine-readable component names
- `missing_reasons`: stable machine-readable reasons
- `estimated_components`: components currently relying on assumptions
- `actual_components`: components backed by recorded/provider data

A zero amount is never sufficient to infer availability. Availability comes from the resolver result.

## 7. Persistence

### 7.1 StoreUnitEconomicsConfig

Create a dedicated model/table instead of adding financial-policy columns to `Store`.

Conceptual fields:

- `id`
- `organization_id` — required, indexed, FK organizations
- `store_id` — required, unique, indexed, FK stores
- `outbound_shipping_cost` — nullable numeric(18,4)
- `return_logistics_cost` — nullable numeric(18,4)
- `default_payment_fee_percent` — nullable numeric with sufficient decimal precision
- `default_payment_fee_fixed` — nullable numeric(18,4)
- `default_cod_fee_percent` — nullable numeric with sufficient decimal precision
- `created_at`
- `updated_at`

All monetary configuration values are denominated in the store currency. The configuration does not store a second mutable currency field; changing store currency requires explicit handling described below.

Validation:

- monetary values >= 0
- percentage values >= 0 and <= 100
- tenant/store ownership enforced
- at most one configuration row per store

### 7.2 PaymentMethodCostRule

Create a child model/table for method-specific overrides.

Conceptual fields:

- `id`
- `organization_id`
- `store_id`
- `unit_economics_config_id`
- `payment_method` — normalized key, max length aligned to `Order.payment_method`
- `fee_percent` — nullable
- `fee_fixed` — nullable
- `is_cod` — boolean, default false
- `cod_fee_percent` — nullable
- `created_at`
- `updated_at`

Constraints:

- unique `(store_id, payment_method)`
- non-negative monetary values
- percentages between 0 and 100
- rule ownership must match its parent config's organization/store

Payment method normalization for matching is `strip().casefold()` at the service boundary. Configuration writes must reject an empty normalized method.

### 7.3 Store currency changes

Because estimates are stored in the store currency, changing `Store.currency` can invalidate monetary assumptions.

V2.2 must not silently reinterpret configured monetary values in the new currency.

When a store with Unit Economics monetary estimates changes currency, the store update flow must either:

1. clear monetary Unit Economics estimates and require reconfiguration, or
2. reject the currency change with a conflict until Unit Economics estimates are cleared.

The implementation plan should use option 1 because it preserves the existing ability to edit a store while preventing cross-currency reinterpretation. Percentage-only values may remain, but fixed monetary values (`outbound_shipping_cost`, `return_logistics_cost`, `default_payment_fee_fixed`, and method `fee_fixed`) must be cleared transactionally with the currency change.

No FX conversion is performed.

## 8. Service architecture

Business logic remains in `backend/app/services/`.

Recommended service boundaries:

### `unit_economics_config_service`

Responsibilities:

- read/create/update store configuration;
- validate numeric ranges;
- normalize payment-method rules;
- enforce organization/store ownership;
- return a stable config DTO.

### `dropshipping_unit_economics`

Responsibilities:

- load the exact order cohort;
- reuse existing delivered revenue/COGS semantics where practical;
- compute lifecycle-sensitive operating costs;
- resolve default vs method-specific estimates;
- fetch/resolve store-level Meta spend;
- produce completeness/provenance metadata;
- never mutate business records.

### Meta spend helper

Provider HTTP remains in the existing Meta Ads client. Unit Economics may add a service-level helper around the client to resolve exact-period spend, currency validation, errors, and provenance. Provider HTTP must not be moved into API routers.

## 9. API contracts

### 9.1 GET configuration

`GET /api/stores/{store_id}/unit-economics/config`

Permission: `stores.read`.

Behavior:

- validates active tenant/store ownership consistently with store-management APIs;
- returns a stable empty/default DTO when no persisted config exists rather than creating a row during GET;
- includes store currency;
- includes normalized payment-method rules.

### 9.2 PUT configuration

`PUT /api/stores/{store_id}/unit-economics/config`

Permission: `stores.write`.

Behavior:

- full replacement/upsert of store defaults and method rules;
- transactionally replaces stale method overrides;
- validates tenant/store ownership;
- validates percentages and amounts;
- rejects duplicate normalized payment-method keys;
- does not permit a currency in the payload different from the store currency.

A full-replacement PUT is preferred over piecemeal PATCH for V2.2 because the editable object is small and it avoids stale overrides surviving unintentionally.

### 9.3 GET analytics

`GET /api/stores/{store_id}/analytics/dropshipping/unit-economics?date_from=...&date_to=...`

Permission: `analytics.read`.

Store isolation and date parsing follow the existing dropshipping analytics endpoints.

Illustrative response shape:

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
      "reason": null
    },
    "outbound_shipping": {
      "amount": 180000.0,
      "source": "estimated",
      "status": "available",
      "reason": null
    },
    "payment_fees": {
      "amount": 92000.0,
      "source": "estimated",
      "status": "available",
      "reason": null
    },
    "cod_fees": {
      "amount": 21000.0,
      "source": "estimated",
      "status": "available",
      "reason": null
    },
    "reverse_logistics": {
      "amount": 36000.0,
      "source": "estimated",
      "status": "available",
      "reason": null
    },
    "ad_spend": {
      "amount": null,
      "source": "missing",
      "status": "missing",
      "reason": "meta_not_connected"
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

Exact serialization details may use the repository's established float/decimal conventions, but API tests must prevent NaN/Infinity and ambiguous zero-as-missing behavior.

## 10. Frontend configuration UX

Settings are the single editable source of Unit Economics assumptions.

The existing store configuration experience is the natural store-specific Settings surface. Add a **Unit Economics** section to store configuration rather than building a second editable form inside Analytics.

Fields:

- average outbound shipping cost
- average reverse-logistics cost
- default payment fee percentage
- default payment fixed fee
- default COD fee percentage
- payment method overrides table
  - method key
  - payment fee %
  - fixed fee
  - COD toggle
  - COD fee %

UX requirements:

- show store currency beside every fixed monetary field;
- explain that configured values are estimates;
- show validation inline;
- support removing an estimate to return that component to `missing`;
- support deleting an override;
- localize ES, EN, and PT-BR;
- require `stores.write` for editing; read-only users may view configuration when allowed by the existing Settings model.

## 11. Analytics UX

Add an **Economía real / Unit Economics / Economia unitária** section near the existing delivered-profitability section.

Display:

- delivered/recognized revenue
- COGS
- gross profit
- outbound shipping
- payment fees
- COD fees
- reverse logistics
- Meta Ads spend
- contribution profit
- contribution margin

Each cost row should expose a compact source badge:

- Actual
- Estimado
- Falta dato

When complete, Contribution Profit and Contribution Margin are visually emphasized.

When incomplete:

- show `Contribution Margin — Incomplete` instead of a misleading percentage;
- leave final contribution values visually unavailable (`—`), backed by `null` in the API;
- list the missing components/reasons;
- keep known component values visible;
- provide a context-specific CTA such as `Configure costs` or `Connect Meta Ads`;
- the `Configure costs` CTA navigates to the selected store's Unit Economics Settings section.

Meta currency mismatch must display both currencies when available so the user understands why spend was excluded.

## 12. Dashboard resilience

The current dropshipping dashboard loads independent analytics sections with `Promise.allSettled`.

Unit Economics becomes an additional independent analytics section.

Requirements:

- a Unit Economics failure must not hide overview, profitability, products, orders, or Decision Intelligence;
- the partial-unavailable banner includes Unit Economics when its request fails;
- an incomplete financial result is **not** a request failure and should render normally with its data-quality warning;
- only transport/server failures mark the section unavailable.

## 13. Security and tenancy

Every config and analytics query must be constrained by both:

- `organization_id`
- `store_id`

A store from another organization, deleted store, or otherwise inaccessible store must not expose configuration or financial data.

Use established repository permission gates:

- config read: `stores.read`
- config write: `stores.write`
- analytics: `analytics.read`

Never trust `organization_id` or currency supplied by the frontend.

## 14. Error handling

### Configuration

- invalid negative amount: 422
- percentage outside 0..100: 422
- duplicate normalized method rule: 422
- inaccessible store: repository-consistent 404
- insufficient permission: 403

### Analytics

Provider failures from Meta are data-quality conditions, not whole-endpoint failures, when commerce analytics can still be computed.

Examples:

- Meta timeout -> `ad_spend missing/provider_error`; endpoint remains 200
- Meta disconnected -> `ad_spend missing/meta_not_connected`; endpoint remains 200
- Meta/store currency mismatch -> 200 incomplete response

Database/service failures unrelated to an optional external cost source may still fail the endpoint normally.

Provider error text must not leak secrets or raw tokens.

## 15. Testing strategy

Implementation follows TDD.

### Backend model/migration tests

Verify:

- one config per store;
- unique normalized payment method rule behavior at service/API level;
- tenant ownership;
- numeric constraints/validation;
- delete/cascade behavior appropriate to store deletion;
- migration upgrade works on supported database path.

### Configuration service/API tests

Verify:

- empty config GET;
- upsert/full replacement;
- clearing nullable estimates;
- default + override serialization;
- duplicate normalized methods rejected;
- foreign store rejected;
- permissions;
- store currency change clears fixed monetary estimates transactionally.

### Unit economics service tests

At minimum cover:

1. all components complete with estimated shipping/payment/COD/returns and actual Meta spend;
2. COGS incomplete -> final contribution withheld;
3. Meta disconnected -> final contribution withheld;
4. Meta currency mismatch -> final contribution withheld;
5. Meta provider failure -> 200-compatible missing ad spend result;
6. successful Meta response with zero spend -> actual zero, not missing;
7. delivered order cost treatment;
8. returned order revenue/COGS zero + outbound/reverse logistics;
9. cancelled order zero direct operating costs;
10. shipped/confirmed orders excluded from recognized contribution costs/revenue;
11. payment method override beats defaults;
12. partial override falls back field-by-field to defaults;
13. COD only applies to configured COD methods;
14. no COD estimate for returned/cancelled orders;
15. payment method absent and no default -> payment fees missing;
16. no returned orders -> reverse logistics known zero/not applicable;
17. zero recognized revenue -> margin null without NaN/Infinity;
18. exact date range and inclusive date-only end semantics;
19. strict tenant/store isolation.

### Meta range tests

Characterize the existing client and verify conversion from analytics half-open datetime range to Meta calendar `time_range`, especially one-day and month-boundary ranges.

### Frontend tests

Verify:

- ES/EN/PT-BR labels;
- source badges;
- complete result displays contribution profit/margin;
- incomplete result never displays a fabricated contribution percentage;
- missing Meta CTA;
- missing config CTA;
- currency mismatch messaging;
- Settings form validation and method overrides;
- Unit Economics request failure does not break other dashboard sections;
- incomplete response is rendered, not treated as unavailable.

### Regression

Existing dropshipping overview, profitability, Product Analytics V2, Decision Intelligence V2.1, Meta Ads analytics, store configuration, permissions, and route-contract tests must remain green.

## 16. Observability

Log enough structured information to diagnose provider/data-quality problems without exposing credentials:

- organization/store ids
- selected date range
- Meta availability state/reason
- Meta account/store currencies when mismatched
- completeness status
- missing component names

Do not log access tokens, encrypted secrets, customer payment details, or raw provider authentication payloads.

## 17. Rollout and compatibility

The migration creates nullable configuration. Existing stores therefore begin with no estimated operating-cost assumptions.

Consequences after deployment:

- existing gross-profit analytics continue to work unchanged;
- Unit Economics may initially be incomplete;
- users explicitly configure shipping/payment/return assumptions;
- users connect Meta Ads to complete ad spend;
- no historical data backfill is required;
- no synthetic default costs are seeded.

This avoids silently changing profitability for existing tenants.

## 18. Acceptance criteria

V2.2 is complete when:

1. a store can persist default Unit Economics assumptions and payment-method overrides;
2. fixed monetary assumptions are never silently reinterpreted after a store-currency change;
3. analytics computes the approved lifecycle-based cost model for a selected period;
4. Meta spend is fetched for the exact bounded period and only accepted in matching currency;
5. each cost exposes actual/estimated/missing provenance;
6. any missing mandatory component withholds final contribution profit and margin;
7. successful zero-cost provider results are distinguishable from missing data;
8. returned and cancelled orders obey the approved rules;
9. Settings is the only editable source for assumptions;
10. Analytics provides an appropriate shortcut to Settings/Meta integration;
11. Unit Economics failures are isolated from the rest of the dropshipping dashboard;
12. tenant isolation and existing permissions are enforced;
13. ES, EN, and PT-BR presentation is supported;
14. all targeted and full regression tests pass.
