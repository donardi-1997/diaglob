# Operations Center Health Design

**Approved:** 2026-09-11

## Goal

Turn the existing Operations Center into a trustworthy operational status surface. Keep the current real-data aggregation and add an explicit backend-owned health contract, accurate AI metric semantics, localized status presentation, periodic refresh, and prioritized alerts.

## Backend contract

The operations summary will expose a top-level `health` object:

```json
{
  "status": "operational | attention | degraded",
  "issues": 0,
  "critical_issues": 0
}
```

Health is derived from real summary data rather than UI heuristics.

- `degraded`: one or more integration status reads are degraded/unavailable.
- `attention`: no degraded dependency exists, but there are actionable operational warnings such as failed automations in the last 7 days or orders with `external_creation_status=unknown`.
- `operational`: neither degraded dependencies nor actionable warning conditions are present.
- Informational setup alerts (for example, no commerce connection yet) do not by themselves make the store unhealthy.

`issues` counts actionable warning/degraded conditions represented by the health calculation. `critical_issues` counts degraded dependency conditions.

## AI metric semantics

The existing `ai_resolved_pct` name is misleading because it is computed from AI-vs-user message volume, not conversation resolution. Replace it with `ai_message_share_pct`. The UI will label it as AI message share rather than resolution rate.

## Frontend

- Render the hero status from `health.status` instead of a hardcoded “Operational”.
- Localize operational/attention/degraded labels in Spanish, English, and Portuguese.
- Keep the existing KPI cards, changing only the AI metric copy to match `ai_message_share_pct`.
- Sort alerts by severity (`error`, `warning`, `info`) before rendering.
- Add a manual refresh action and automatically refresh the summary every 30 seconds while the dashboard is mounted.
- Background refresh must preserve the currently rendered data rather than replacing it with the initial skeleton.
- Keep integration failure semantics: unavailable status is degraded, never falsely disconnected.

## Scope constraints

- No database migrations.
- Do not modify `backend/app/models.py`.
- Preserve tenant/store isolation.
- Preserve the existing operations summary endpoint and permission model.
- Business-health rules live in backend services, not the React page.
- Use TDD for behavior changes.
- Run focused backend tests, frontend tests/build, and final PR CI before merge.
