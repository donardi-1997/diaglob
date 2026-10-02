# Multi-carrier tracking

Diaglob uses one canonical shipment model for supplier tracking, local carriers,
last-mile delivery, post-sales, and automation events.

## Current Colombia coverage

The registry currently includes:

- Coordinadora
- Servientrega
- Inter Rapidísimo
- TCC

This first production slice implements the carrier-neutral tracking runtime and
a signed webhook bridge for all four carriers. It does **not** claim that each
carrier's proprietary API/webhook payload is already implemented.

The registry separately exposes whether an official API surface has been
identified so a native adapter can be added without changing Shipment,
TrackingEvent, Flow Builder, or the Commerce UI.

## Architecture

```text
Supplier / Shopify / carrier
        |
        v
Carrier adapter / normalized webhook
        |
        v
Shipment + TrackingEvent
        |
        v
Canonical status events
        |
        +--> Commerce > Shipments
        +--> Flow Builder
        +--> Post-sales
        +--> Customer notifications
```

CJ remains supported through the existing `sync_cj_shipment` implementation.
The generic shipment API delegates to it when the shipment belongs to CJ.

Carrier-native shipments use the carrier key as `Shipment.provider`.

## Canonical statuses

Adapters normalize provider status data into:

- PENDING
- SHIPPED
- IN_TRANSIT
- CUSTOMS
- OUT_FOR_DELIVERY
- READY_FOR_PICKUP
- DELIVERED
- DELAYED
- FAILED
- EXCEPTION
- RETURNED

Spanish labels such as `En reparto`, `Entregado`, `No entregado`,
`Novedad`, and `En tránsito` are normalized by the common carrier registry.

## Connecting a carrier bridge

Authenticated store users with `stores.write` can connect a carrier with:

```http
POST /api/stores/{store_id}/carriers/{carrier_key}/connect
Content-Type: application/json

{
  "integration_mode": "webhook"
}
```

The response contains a callback URL and a one-time token. Only a SHA-256 hash
of the token is stored. Reconnecting rotates the token.

The callback is shaped as:

```text
POST /api/webhooks/carriers/{carrier_key}/{webhook_token}
```

The token is scoped to one store and one carrier. It cannot update shipments
belonging to a different carrier connection.

## Normalized webhook contract

Provider adapters send:

```json
{
  "tracking_number": "GUIA-123",
  "status": "OUT_FOR_DELIVERY",
  "status_label": "En reparto",
  "source_event_id": "provider-event-908",
  "event_at": "2026-10-02T15:00:00Z",
  "location": "Medellín",
  "description": "En ruta para entrega",
  "tracking_url": "https://carrier.example/GUIA-123",
  "destination_country_code": "CO",
  "order_id": 123
}
```

`source_event_id` is strongly recommended. Diaglob hashes it into the
`TrackingEvent.provider_event_key`, making repeated delivery idempotent. When
it is absent, Diaglob derives a deterministic key from the normalized event
payload.

A webhook can create a carrier shipment when `order_id` is supplied. Otherwise
the tracking number must already be registered.

## Shipment APIs

- `GET /api/carriers`
- `POST /api/carriers/detect`
- `GET /api/stores/{store_id}/carriers`
- `GET /api/stores/{store_id}/shipments`
- `POST /api/stores/{store_id}/shipments`
- `GET /api/stores/{store_id}/shipments/{shipment_id}`
- `POST /api/stores/{store_id}/shipments/{shipment_id}/sync`

Tracking-number-only carrier detection is deliberately conservative. Colombian
guide formats can overlap, so Diaglob prefers an explicit carrier hint rather
than guessing and corrupting delivery state.

## Flow Builder

Canonical shipment events already drive durable Flow Builder triggers:

- shipment_created
- shipment_in_transit
- shipment_out_for_delivery
- shipment_delivered
- shipment_delayed
- shipment_failed
- shipment_delivery_exception
- shipment_returned

Durable flow context exposes:

- `{{shipment.id}}`
- `{{shipment.provider}}`
- `{{shipment.carrier}}`
- `{{shipment.tracking_number}}`
- `{{shipment.last_mile_tracking_number}}`
- `{{shipment.status}}`
- `{{shipment.destination_country}}`
- `{{shipment.delivery_days}}`
- `{{shipment.tracking_url}}`

Message nodes, call nodes, conditions, and tool arguments use the same frozen
runtime context.

Two ready-made templates are included:

- notify when an order is out for delivery
- post-delivery follow-up

## Next native adapters

Native carrier adapters should translate proprietary authentication, polling,
and webhook payloads into the normalized contract above. They should not add
carrier-specific statuses to the rest of Diaglob.

The intended priority is:

1. Coordinadora
2. Inter Rapidísimo
3. TCC
4. Servientrega, once a supported integration contract/credential path is
   available

Direct adapters must use encrypted credentials and must not store secrets inside
`CarrierConnection.provider_config`.
