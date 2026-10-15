# Shopify privacy: request-bound encrypted fixture handoff (2026-10-15)

**Status: synthetic integration harness only; NOT approved for live fulfillment.**

## Security gap addressed

The prior fixture delivery checked a ciphertext hash and the destination merchant
membership, but the sealed fixture was not cryptographically tied to the
specific signed Shopify privacy request. A valid fixture prepared for one case
could be issued under another case for the same merchant/store because neither
the fixture envelope nor issuance checked the sealed request identity.

This PR hardens the **synthetic-only** contract:

1. The source manifest must carry a 64-character opaque `request_id` and retain
   `scope_preview_only`, `export_generated=false`,
   `delivery_authorized=false`, `fulfillment_complete=false`.
2. The builder creates a bounded Fernet-encrypted, versioned envelope including
   that exact request ID; all records and values must have synthetic markers.
3. Fixture issuance independently authenticates the recipient and signed case,
   decrypts the sealed envelope using the fixture delivery key, compares its
   authenticated request ID to the requested case, enforces its source/value
   contract and hash integrity, and only then stores the encrypted artifact.
   Changing the dataclass metadata, swapping encrypted case payloads, supplying
   a wrong key, or placing real personal values in a fabricated record fails
   closed without issuing a ticket.
4. The existing delivery token remains short-lived, single-use, scoped to the
   recipient/organization/store/case and revocable. All retained data is
   encrypted at rest, with minimal audit events and no raw customer content.

**Important implementation detail:** the synthetic export encryption key and
the synthetic delivery encryption key must be the same for cryptographic
envelope verification; the tests use `SHOPIFY_PRIVACY_DELIVERY_KEY` only in
ephemeral SQLite fixtures. Do not issue or expose the actual delivery key to a
real data subject. Future live delivery needs a reviewed key-management and
recipient-delivery design, distinct from this test-only model.

## End-to-end test scope

`backend/tests/test_shopify_privacy_secure_delivery.py` exercises synthetic
signed receipt + local customer/store mapping + preview manifest + fabricated
records + Fernet envelope + authenticated merchant ticket + one-time redemption.
Additional tests reject swapped request identities, spoofed metadata, unreadable
ciphertext, and embedded non-synthetic customer values. The original protected
Cognito HTTP endpoint remains synthetic-only.

Run locally or through CI:

```bash
cd backend
pytest -q tests/test_shopify_privacy_synthetic_export.py tests/test_shopify_privacy_secure_delivery.py tests/test_shopify_privacy_case_assessment.py tests/test_shopify_privacy_local_processor.py
```

## Unchanged release blockers

- This is **not** an export of real buyer data; production DB issuance and
  redemption remain disabled. Synthetic fixture proof is not GDPR fulfillment.
- Field ownership and completeness across local shared customer records,
  order items, chat messages, AI agents, automation, files and vendors remain
  under review.
- Need audited legal retention decisions, end-user/merchant authorization,
  production cryptographic key management and trustworthy external processor
  provenance, buyer delivery acknowledgments, deletion/retention, backup
  restore drills and verified live Shopify subscription/webhooks.
- No AWS spending or infrastructure change in this PR.

Reference: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
