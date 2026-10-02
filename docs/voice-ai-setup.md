# Voice AI outbound calls

Diaglob's Flow Builder supports asynchronous `call` nodes for outbound AI voice calls.

## Runtime model

A call node:

1. Starts one outbound call through the configured provider adapter.
2. Persists the provider `call_id` in `AutomationNodeExecution`.
3. Puts the recipient execution in `waiting`.
4. Resumes when the provider sends a signed callback.
5. Routes through one of four outcomes:
   - `confirmed`
   - `rejected`
   - `no_answer`
   - `failed`

If no callback arrives before `timeout_minutes`, Diaglob resolves the attempt as
`no_answer`. It does **not** redial automatically, which keeps retries explicit
inside the visual flow.

## Environment variables

Configure the API service with:

```text
DIAGLOB_VOICE_PROVIDER_URL=https://voice-adapter.example.com/calls
DIAGLOB_VOICE_PROVIDER_TOKEN=...
DIAGLOB_PUBLIC_API_URL=https://api.diaglob.tech
DIAGLOB_VOICE_WEBHOOK_SECRET=...
```

Alternatively set `DIAGLOB_VOICE_CALLBACK_URL` explicitly instead of deriving it
from `DIAGLOB_PUBLIC_API_URL`.

The Flow Builder only marks voice templates as available when both the provider
configuration and callback secret are present.

## Provider adapter contract

Diaglob sends:

```json
{
  "to": "+573001112233",
  "prompt": "Hola Ana, ...",
  "language": "es",
  "callback_url": "https://api.diaglob.tech/api/voice/callback",
  "outcomes": ["confirmed", "rejected", "no_answer", "failed"],
  "metadata": {
    "organization_id": 1,
    "store_id": 2,
    "flow_run_id": 10,
    "flow_recipient_id": 25,
    "node_id": "call",
    "customer_id": 7
  }
}
```

The adapter must return HTTP 2xx JSON with either `call_id` or `id`.

Diaglob also sends an `Idempotency-Key` header. Providers/adapters should honor
it so a transient HTTP retry cannot create a duplicate phone call.

## Callback contract

The provider sends:

```http
POST /api/voice/callback
X-Diaglob-Voice-Secret: <DIAGLOB_VOICE_WEBHOOK_SECRET>
Content-Type: application/json
```

```json
{
  "call_id": "provider-call-123",
  "status": "completed",
  "outcome": "confirmed",
  "transcript": "Sí, deseo recibirlo."
}
```

Callbacks are idempotent. Repeating a terminal callback does not move the flow
again.

## Current scope

This slice implements the Diaglob runtime and a provider-neutral adapter
contract. It intentionally does not hard-code Twilio, Amazon Connect, ElevenLabs,
or another telephony vendor. A concrete provider can be attached without
changing Flow Builder semantics.

Order-triggered flows now persist a normalized snapshot in
`AutomationFlowRun.trigger_context`. Voice scripts and flow conditions can use
the exact order that fired the flow without re-querying mutable business state.

Available order variables include:

- `{{order.id}}`, `{{order.number}}`
- `{{order.total}}`, `{{order.currency}}`
- `{{order.payment_method}}`, `{{order.payment_status}}`, `{{order.is_cod}}`
- `{{order.shipping.city}}`, province, country, address and zip
- `{{order.items_summary}}`

When a call node uses `call_purpose=order_confirmation`, terminal outcomes are
persisted on the order. A confirmed COD order is eligible for the existing
Shopify -> CJ auto-fulfillment pipeline. The dedicated Flow Builder action
`fulfillment.enqueue_trigger_order` can only enqueue the order stored in the
run's trigger context; it cannot target an arbitrary order ID.

The one-click COD template requires Voice, Shopify, and CJ auto-fulfillment to
be connected before it can be created.
