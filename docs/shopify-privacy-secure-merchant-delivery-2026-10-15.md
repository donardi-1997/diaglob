# Shopify privacy — authenticated encrypted delivery transport

**Status: SYNTHETIC-ONLY; live disclosure disabled.** This is a technically
inspectable step toward `customers/data_request` fulfillment. It does NOT
constitute real GDPR export, delivery to a merchant or Shopify App Store approval.

## Architecture implemented

- Models: `shopify_privacy_delivery_artifacts` stores recipient/user/tenant/store
  bindings, a **SHA-256 digest of a 256-bit random token**, encrypted ciphertext
  (wrapped by independent `SHOPIFY_PRIVACY_DELIVERY_KEY`), issue timestamp,
  expiry, revocation/redemption timestamps, and artifact SHA-256. No raw
  token, plaintext buyer data or recipient email is persisted.
- `shopify_privacy_delivery_audit` stores only request receipt digest,
  action (issued/redeemed/revoked/purged), actor class and timestamp.
- Claim: atomic conditional SQL UPDATE from unconsumed to consumed; ciphertext
  is decrypted in-process only after validating current membership, owner/admin
  role, exact store, signed Shopify receipt, matching token, expiry and status.
  The encrypted-at-rest blob is nulled before committing a successful claim.
- GET endpoint `/api/stores/{store_id}/shopify/privacy/cases/{request_id}/delivery`
  requires authenticated Cognito Bearer plus `X-Privacy-Delivery-Token`.
  Returns ONLY synthetic encrypted bytes, with `Cache-Control: no-store`,
  `nosniff` and `Content-Disposition: attachment`; tokens never enter URLs.
- POST to `.../delivery/revoke` supports identical authentication,
  recipient binding and irreversible removal of ciphertext.
- Expired artifacts are individually unusable and can be purged using
  `purge_expired_synthetic_deliveries`. The cleanup function is provided,
  **but no schedule exists yet**.
- Issuance is **not exposed via HTTP** and accepts only the exact trusted
  `EncryptedSyntheticExport` fixture type. All staging, redemption, revocation
  and cleanup paths require a *real SQLite in-memory engine* plus the explicit
  `SHOPIFY_PRIVACY_SYNTHETIC_HTTP_ENABLED=true` flag. Production PostgreSQL/
  persistent SQLite will always return `LIVE_PRIVACY_DELIVERY_DISABLED`.

## Security tests

Test: cross-merchant, cross-tenant, cross-store, restricted store memberships,
operator role denial, unsigned/wrong-topic receipt, missing Bearer, expired
token, wrong hash, wrong Fernet key, repeat redemption, revocation and no-cache
headers. Test data must be fabricated and never sourced from actual customers.

## What remains NO-GO

1. Exact Shopify ID/installation provenance verified on real OAuth installation,
   including post-uninstall lifecycle and changed-owner arbitration.
2. Complete export including all tables, Copilot/automation payloads, S3,
   shipping/supplier providers, AI-derived fields, logs and legally retained data.
3. Genuine independent legal retention/processor approval; protect data subject
   and recipient identity; enforce verified merchant owner permissions and
   ability to deliver to merchant even after uninstall.
4. Separate protected artifact storage/key management, expiry scheduler and
   backup/resurrection policy. The current DB vault is **not** an independently
   operated secure object store.
5. Real encrypted export with merchant-accessible secure download and confirmed
   receipt, not synthetic ciphertext requiring an out-of-band fixture key;
   review completion evidence and update only after actual fulfillment.
6. Tests of the three active Shopify compliance subscriptions on staging/live.

The presence of a new API route is not authorization to flip these safeguards.
Do not deploy, merge to main, or run migration in production without
maintenance window, backup/restore plan and explicit operational approval.

Official source: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
