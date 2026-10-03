# Diaglob Growth Acquisition Architecture

This workspace is for acquiring Diaglob customers. It is intentionally separate
from the Meta Ads integrations that Diaglob merchants connect to their own stores.

## Objective

Measure the full path from paid impression to paid Diaglob customer:

```
Meta campaign
  -> landing visit
  -> registration started
  -> lead / registration submitted
  -> registration completed
  -> trial activated
  -> paid subscription
```

## Phase 1 — attribution and conversion quality

Implemented foundation:

- Consent-gated Meta Pixel and TikTok Pixel.
- First-touch and last-touch UTM capture.
- `fbclid` / `ttclid` capture.
- Meta Pixel `ViewContent`, `Lead`, and `CompleteRegistration`.
- Server-side Meta Conversions API for `CompleteRegistration`.
- Pixel/CAPI deduplication with a shared `event_id`.
- Registration attribution persisted without raw email/IP/user-agent storage.
- Platform-admin acquisition summaries by source, campaign, and CAPI status.

## Phase 2 — growth dashboard

Add an internal Diaglob admin workspace with:

- Spend.
- Impressions.
- CTR / CPC / CPM.
- Registrations.
- Cost per registration.
- Trials activated.
- Paid subscriptions.
- CAC.
- Revenue and payback.
- Campaign, ad set, and creative breakdown.

Meta Insights should be joined with Diaglob registration/subscription outcomes by
UTM campaign/content conventions rather than mixing this data with merchant ad
accounts.

## Phase 3 — campaign operations

Use the Meta Marketing API from a Diaglob-owned ad account to support:

- campaign creation,
- ad-set creation,
- creative creation,
- budget updates,
- pause/resume,
- Insights synchronization.

All write operations should remain approval-gated. The existing merchant
`meta_ads_service` must not be reused for Diaglob's corporate acquisition account;
create a dedicated growth service/configuration boundary.

## Phase 4 — creative factory

Create a reusable creative brief:

- audience,
- pain point,
- promise,
- proof,
- hook,
- CTA,
- format,
- destination URL,
- UTM content identifier.

Generate multiple copy and creative variants, but require a human approval step
before publishing them to Meta.

Recommended first campaign content IDs:

- `chaos_tools_v1`
- `shopify_automation_v1`
- `ai_copilot_v1`
- `product_demo_v1`

## Phase 5 — lead follow-up

For visitors who become leads but do not activate:

- email follow-up,
- optional WhatsApp follow-up after explicit opt-in,
- demo request workflow,
- CRM stage,
- lead score,
- trial activation and conversion events.

Diaglob's existing automation engine can own the orchestration. Do not introduce
n8n into the customer-facing product solely for this internal growth workflow.
