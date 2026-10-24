# Shopify offline token migration — one-store runbook

**Scope:** migrate one *existing, tenant-bound* non-expiring Shopify offline token to a renewable pair. This is separate from the fixes for **new** OAuth grants (PR #315). It never modifies app pricing, billing or paid entitlements.

Official protocol: https://shopify.dev/docs/apps/build/authentication-authorization/migrate-to-expiring-offline-access-tokens

## Before running

1. Confirm the OAuth code-grant and refresh-token changes are deployed and production readiness is green.
2. Ensure the shop is a verified existing connection in **DIAGLOB's own database**, not merely an installation shown in Shopify Dev Dashboard.
3. Ensure production environment contains the correct `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET` and `SHOPIFY_TOKEN_ENCRYPTION_KEY`. No secrets may appear in shell history, command-line arguments, saved output or support tickets.
4. Confirm a recent secure database backup exists. Do not export decrypted Shopify credentials.
5. Do not simultaneously refresh, reauthorize, reinstall or claim a Shopify token for the same store. A new acquisition can retire the pair being migrated.

## Phase A — read-only audit

On the authorized DIAGLOB production server, from `/opt/diaglob/app/backend`, with the normal secured environment already loaded:

```bash
.venv/bin/python -m scripts.migrate_shopify_legacy_offline_token \
  --shop diaglob-poc.myshopify.com
```

The command **must not decrypt or print credentials, contact Shopify, or modify the database**. It prints the exact `connection_id`, `organization_id`, `store_id` and an eligibility result. Read-only classifications:

- `READY_FOR_DIRECT_MIGRATION`: an active or recoverable DIAGLOB connection has a legacy access-only token.
- `ALREADY_EXPIRING`: no direct migration needed; inspect refresh behavior instead.
- `INCONSISTENT_TOKEN_STATE`: manual reconciliation required; do not run apply.
- `SHOPIFY_CONNECTION_NOT_FOUND`: Shopify may show an installation, but no tenant-bound connection exists in DIAGLOB; do not create a link from the shop domain alone.
- `NO_STORED_ACCESS_TOKEN` or `CONNECTION_NOT_ACTIVE`: correct the underlying state before proceeding.

## Phase B — one-time live exchange (requires explicit approval)

**Warning:** The successful Shopify exchange invalidates the previous offline token. The script encrypts and commits the new pair in one targeted database transaction; it has no rollback for provider-side invalidation. Do not run until Phase A and production backups are verified.

Use the IDs shown by Phase A, then run:

```bash
.venv/bin/python -m scripts.migrate_shopify_legacy_offline_token \
  --shop diaglob-poc.myshopify.com \
  --apply \
  --connection-id YOUR_VERIFIED_CONNECTION_ID \
  --organization-id YOUR_VERIFIED_ORGANIZATION_ID \
  --acknowledge-token-invalidation
```

Successful output is `MIGRATED` without tokens. `MIGRATED_SCOPES_REQUIRE_REVIEW` means the new pair was persisted but the connection was set to `error` because the returned Shopify scopes were insufficient: reauthorize via the secure managed installation flow, **do not** downgrade the scope check.

## Phase C — verification

1. Rerun Phase A: state must now be `ALREADY_EXPIRING`.
2. Test the Shopify connection and a read-only Admin GraphQL query from the normal authenticated DIAGLOB flow. Confirm no refresh or scope errors.
3. Verify encrypted refresh token and both expiry timestamps are non-null through a metadata-only DB inspection; never print ciphertexts.
4. Verify an automatic refresh when the access token nears expiry, with a new encrypted refresh token saved.
5. Recheck the obsolete-offline-token warning in Shopify Dev Dashboard. The UI may lag behind the migration.

## Failure and recovery

If Shopify returns an invalid legacy token, **do not** repeatedly retry uncontrolled or uninstall. Verify app identity, installation provenance and whether the token is already expiring.

If Shopify accepted the exchange but the DB write failed, the script returns `*_RECOVERY_REQUIRED`. Shopify documents a **limited seven-day response recovery** by repeating the original migration request with the same legacy token, but recovery stops after refresh or another token acquisition. Preserve server logs with stable error codes only, and prioritize recovery before other token activity. If recovery is unavailable, issue a new expiring token through verified embedded token exchange or a fresh authorization code grant.

**Do not mark the Shopify alert as closed** until one store is actually migrated and the read-only API check passes.
