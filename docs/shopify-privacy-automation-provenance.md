# Shopify customer privacy: automation provenance and Copilot gap

**Development only. This is read-only impact counting, not a complete customer
export/redaction feature or a statement of Shopify App Store readiness.**

The `inspect_shopify_automation_privacy_impact` service first validates the
signed request's original Shopify store/tenant identity using the existing
scope-preview guard. For `customers/data_request` and `customers/redact`, it
then resolves the exact Shopify external customer ID from the encrypted
selector through that store's customer profile. No email, phone, names,
message bodies or AI text is used as an identity key.

It counts only records that are linked by foreign keys to the matching
customer **and** verified originating store/organization, covering:

- Campaign audience membership, campaign recipient execution and delivery attempts
- Visual automation flow recipient executions and their node executions

For `shop/redact`, the impact includes all recipient records of the verified
store, including those not currently present in a customer profile. No other
store, even one in the same tenant sharing the same customer row, is counted.
All results are aggregate counts without Shopify/customer IDs, recipient
payloads, provider message identifiers or decrypted text.

The following **remain uncovered**, even if these count results are nonzero:
rendered campaign messages, template JSON and error text; flow trigger context,
execution/extra_data payloads, legacy automations with free-form JSON, queued
or already-delivered provider messages, and backups/retention/legal holds.

**Copilot distinction:** `AgentChatSession` is connected to a merchant
membership/user, not directly to the Shopify customer in a signed GDPR
request. `AgentChatMessage` and tool JSON may contain copied customer data
but cannot be safely exported or erased for that buyer by searching free text,
email or phone. A separate verified provenance mechanism and legal processing
policy are required. No Copilot records are touched or identified here.

Safety characteristics: no new endpoint, scheduler or worker, no migration,
no SELECT of message bodies, no export and no mutation or Shopify API calls.
The source inventory is still `uncovered` for automations and Copilot
because counting alone is insufficient. Existing legal and live-execution
gates remain unchanged. Tests use synthetic SQLite rows for same-customer
cross-store and cross-tenant isolation, unknown subjects and invalid shop
identity.

Tracks issue #148 and draft PR #149.
