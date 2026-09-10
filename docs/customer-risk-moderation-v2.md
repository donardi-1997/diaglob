# Customer Risk Moderation V2

Customer risk remains a preventive shared signal, never an automated finding of guilt and never an automatic order block.

## Governance invariants

- Tenant-facing responses remain aggregate and never reveal another reporter organization, reporter user, private notes, or private evidence.
- Report and dispute writes are organization-scoped and rate-limited over rolling 24-hour windows.
- Report and dispute lifecycle changes append immutable audit events.
- A dispute does not change an external report by itself. Only a platform-admin resolution can mark matching external reports as disputed.
- Accepting a dispute marks matching pending/confirmed external reports `disputed`; it does not delete reports or automatically block/unblock customers.
- Reporter reputation is moderation-derived and advisory only. It affects queue priority, not customer risk automatically.
- Platform moderation requires an explicit note for every decision.

## Production settings

- `CUSTOMER_RISK_HMAC_SECRET` must stay stable.
- `CUSTOMER_RISK_REPORT_LIMIT_24H` defaults to 25 writes per organization (bounded 1-500).
- `CUSTOMER_RISK_DISPUTE_LIMIT_24H` defaults to 10 writes per organization (bounded 1-200).
- Platform moderation endpoints remain protected by `PLATFORM_ADMIN_EMAILS`.

## Migration

Revision `l8f9a0b1c2d3` extends `k7f8a9b0c1d2` with append-only report/dispute events and customer risk disputes.
