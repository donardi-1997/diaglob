# Meta launch — Diaglob Colombia

## Goal

Acquire Colombian ecommerce and dropshipping operators and measure the full path:

```
Meta ad -> /ecommerce -> CompleteRegistration -> StartTrial -> Subscribe
```

Campaign launches **paused**. Budget and activation require explicit approval because
they cause external spend.

## Naming

- Campaign: `DLB_CO_ACQ_ECOMMERCE_001`
- Ad set: `CO_BROAD_ECOMMERCE_001`
- UTM campaign: `co_launch_2026_q4`
- Destination: `https://diaglob.tech/ecommerce`

## Conversion events

1. `CompleteRegistration`
2. `StartTrial`
3. `Subscribe`

Diaglob's acquisition ledger already stores these events with the original campaign
attribution, so campaign quality can be judged by paid subscriptions rather than CTR
alone.

## Creative variants

### chaos_tools_v1

Primary text:
¿Tu ecommerce vive entre Shopify, Excel, WhatsApp y varias herramientas más? Diaglob reúne operación, automatizaciones, reportes y un copiloto de IA en un solo lugar.

Headline: **Opera tu ecommerce desde un solo lugar**

URL:
`https://diaglob.tech/ecommerce?utm_source=meta&utm_medium=paid_social&utm_campaign=co_launch_2026_q4&utm_content=chaos_tools_v1`

### shopify_automation_v1

Primary text:
Menos tareas manuales. Más control. Centraliza pedidos, clientes y automatizaciones para que tu operación no dependa de revisar cinco pantallas.

Headline: **Automatiza la operación de tu ecommerce**

URL:
`https://diaglob.tech/ecommerce?utm_source=meta&utm_medium=paid_social&utm_campaign=co_launch_2026_q4&utm_content=shopify_automation_v1`

### ai_copilot_v1

Primary text:
Pregúntale a tu ecommerce qué está pasando: pedidos detenidos, clientes pendientes y tareas por automatizar. Diaglob convierte información en acciones.

Headline: **Un copiloto para tu operación ecommerce**

URL:
`https://diaglob.tech/ecommerce?utm_source=meta&utm_medium=paid_social&utm_campaign=co_launch_2026_q4&utm_content=ai_copilot_v1`

### product_demo_v1

Primary text:
Shopify es tu tienda. Diaglob puede ser tu centro de operaciones: pedidos, clientes, automatizaciones, reportes e IA conectados.

Headline: **Tu centro de operaciones ecommerce**

URL:
`https://diaglob.tech/ecommerce?utm_source=meta&utm_medium=paid_social&utm_campaign=co_launch_2026_q4&utm_content=product_demo_v1`

## Launch gate

Do not activate spend until all are true:

- Meta ad account is connected.
- Meta Pixel ID is available to the frontend.
- Conversions API access token is configured in production.
- Events Manager confirms browser/server event deduplication.
- A daily budget has been explicitly approved.
- Campaign, ad set and ads are created in `PAUSED` state first.
