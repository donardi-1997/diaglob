---
name: commerce-integrations
description: Work on Diaglob commerce and dropshipping integrations such as Shopify, Nuvemshop, Dropi, product synchronization, external orders, OAuth, and store-scoped commerce behavior.
compatibility: opencode
metadata:
  project: diaglob
  scope: commerce
---

## Scope

Use this skill for commerce provider integrations, OAuth/connect/disconnect flows, product/variant synchronization, and external order creation.

The repository currently contains commerce-related API modules including `commerce.py`, `dropi.py`, and `nuvemshop.py`. Inspect the concrete provider implementation and tests before editing it.

## Invariants

- A commerce connection must remain scoped to the correct organization/store.
- Never accept a provider product/variant/order identifier as proof that it belongs to the current store; validate ownership using existing mappings/connection context.
- Keep provider tokens encrypted/stored through the existing credential mechanism; never log them.
- OAuth state/HMAC/signature validation must not be weakened.
- Preserve idempotency for external order/resource creation.
- Treat provider success, provider rejection, timeout, and unknown outcome as distinct states where the existing model supports them.
- Do not silently substitute currency, shipping, inventory, variant, or store identifiers.
- Provider-specific behavior belongs behind provider-specific clients/services rather than spreading conditionals throughout unrelated domains.

## Change procedure

1. Trace API route -> service/domain logic -> provider client -> persistence.
2. Inspect tests for the provider and the generic commerce layer.
3. Identify store/tenant and idempotency boundaries.
4. Make the smallest coherent change.
5. Add a regression test for the failure mode.
6. Run targeted provider tests and then the broader backend suite when practical.

## External APIs

Do not guess provider API contracts. Use the repository's current client behavior and authoritative provider documentation when a contract must be verified.
