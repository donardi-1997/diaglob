# Shopify App Pricing · Production rollout and reconciliation

## State checked 2026-10-11
AWS `us-east-2` has Lightsail `diaglob-prod` running, but **no EventBridge Scheduler or EventBridge rule** for Diaglob billing rechecks. There were **no Shopify/Diaglob configuration names** visible in SSM Parameters or Secrets Manager. These searches **do not** inspect Lightsail process environment, Docker files or the Shopify Partner Dashboard. No production settings were changed.

## Correct billing authority
Shopify App Pricing hosts selection and charges in Partner Dashboard. Post-approval redirects may contain `plan_handle`, **which is never proof of payment**. Fetch live `activeSubscription(appId, shopId)` using the Partner API and the Shopify-authenticated shop identity, and require an approved handle/period/price match. Partner API client needs **Manage apps** and the app must be public. New App Pricing subscription changes do **not** send webhooks after 2026-04-28.

Reference: https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing

## Batch reconciliation

The existing `python -m app.shopify_billing_recheck` now scans *all* paid Shopify organizations via keyset pagination. A fresh database session is used per shop; query/filter never includes Paddle. Continue past each failed merchant, but exit with a nonzero code on failure, incomplete pages or disabled feature. Logs include only Diaglob internal organization IDs, not provider errors, handles, tokens or domains.

Example (ONLY AFTER approving all release gates, from configured backend virtualenv):

```bash
cd /path/to/diaglob/backend
python -m app.shopify_billing_recheck --page-size 50 --max-pages 1000
```

**Do not enable or schedule on production just to make this command exit successfully.** The same `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED=true` gate controls paid access application and rechecks.

### Proposed production schedule (not installed)
Use a dedicated, low-overlap hourly service on the Lightsail host after deployment and account approval. Sample systemd unit and timer below. Review path, service account, environment, timeouts and host capacity with the operator first.

```ini
# /etc/systemd/system/diaglob-shopify-billing.service
[Unit]
Description=Diaglob Shopify subscription recheck
[Service]
Type=oneshot
User=diaglob
WorkingDirectory=/opt/diaglob/backend
EnvironmentFile=/etc/diaglob/shopify-billing.env
ExecStart=/opt/diaglob/backend/.venv/bin/python -m app.shopify_billing_recheck --page-size 50 --max-pages 1000
TimeoutStartSec=3000
NoNewPrivileges=yes
```

```ini
# /etc/systemd/system/diaglob-shopify-billing.timer
[Unit]
Description=Hourly Diaglob Shopify subscription recheck
[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120
Unit=diaglob-shopify-billing.service
[Install]
WantedBy=timers.target
```

Monitor journal exit status, failed units, API error rate, DB write count, run duration, unverified merchant age and alerts for runs that are incomplete or don't occur. A timer alone without alerts is not production-ready; this code change does not create the timer or its monitoring.

## Go/no-go checklist

1. Confirm the actual **Diaglob** Partner public app ID, pricing handle, plan amounts, monthly/annual periods, and `Manage apps` Partner API token. Never copy Bakatá's commerce integration credentials.
2. Approve **one Shopify store per billed Diaglob organization** (current implementation fails closed for multiple Shopify merchant bindings); review the desired future multishop model.
3. Verify no-charge Shopify development-store plan selection and Partner API subscription history, cancellation, annual change and reinstall, using the same Partner organization.
4. Configure encrypted operator values: `SHOPIFY_PARTNER_ORG_ID`, `SHOPIFY_PARTNER_APP_GID`, `SHOPIFY_PARTNER_ACCESS_TOKEN`, `SHOPIFY_APP_PRICING_HANDLES_JSON`, `SHOPIFY_APP_STORE_HANDLE`; no secrets in git.
5. Inspect Lightsail deployment/backup, install periodic checks, alert on failures and test a confirmed cancellation. Review privacy P0 separately.
6. Only after explicit release approval, enable `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED=true` and verify controlled merchant E2E. Keep the flag OFF in all other environments.

## Known limitations
Shopify API outages do not automatically revoke a previously active plan; alert on failed checks. Multistore contract behavior remains blocked. Current app does not yet implement free-plan entitlement policy, Shopify-provided invoice exports or automated live merchant acceptance tests.
