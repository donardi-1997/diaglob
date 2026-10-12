# Diaglob — Meta Pixel por tienda · Fase 1 (2026-10-11)

## Alcance entregado

- Persistencia por `organization_id + store_id`, una configuración por tienda, sin confundirla con `MetaAdsConnection` (cuenta publicitaria) ni con el Pixel global de adquisición de Diaglob.
- Endpoints autenticados `GET/PUT/DELETE /api/stores/{store_id}/meta-pixel` con permiso `stores.read/write` y control de membresía por tienda. Un usuario no puede consultar ni editar tiendas que no tiene asignadas.
- Validación del Pixel ID (8–30 dígitos), opción declarativa sobre integración Meta ya existente y aviso de posible duplicación de eventos.
- Tarjeta en Integraciones de cada tienda. Sin token de Meta, sin píxel inyectado en el tema, sin llamadas remotas y sin eventos enviados.
- **Siempre** `enabled=false`, `extension_installed=false`, `status=awaiting_extension`. El estado significa «configuración guardada», **no** «Meta conectado».

## Fase 2 — Web Pixel extension (bloqueada hasta Shopify Partner)

1. Reutilizar la **app existente** de Diaglob, confirmar su versión y el repositorio de extensiones. La extensión requiere un UID real generado por Shopify CLI; **no inventar** UID ni crear una aplicación nueva.
2. Solicitar `write_pixels` y `read_customer_events`; valorar el impacto sobre revisión Shopify y aprobación de permisos.
3. Generar extensión con `shopify app generate extension --template web_pixel`, configurar `runtime_context = "strict"` y privacy purposes `marketing`, `analytics` y `sale_of_data` según el tratamiento de datos.
4. Leer el `pixel_id` específico de la tienda desde los ajustes de la extensión y activar con `webPixelCreate` o actualizar con `webPixelUpdate` en Shopify Admin GraphQL. **Solo** después de consentimiento, scopes, revisión de doble medición y prueba en dev store.
5. Mapeos previstos: `page_viewed` -> `PageView`; `product_viewed` -> `ViewContent`; `product_added_to_cart` -> `AddToCart`; `checkout_started` -> `InitiateCheckout`; `checkout_completed` -> `Purchase`. Valores/monedas y deduplicación por Shopify event ID; no suponer atribución por evento.
6. Conversions API por tienda requiere credencial separada cifrada, aislamiento de tenant y deduplicación browser/servidor con el mismo `event_id`; no reutilizar el token de adquisición de Diaglob.
7. Si la app oficial Facebook & Instagram de Shopify ya dispara eventos, **no** habilitar una segunda fuente con el mismo Pixel antes de resolver duplicados y permisos explícitos.
8. Probar con `diaglob-poc.myshopify.com`, Shopify Settings > Customer events y Meta Events Manager; verificar consentimiento denegado/concedido, compra sintética, reintentos sin duplicación y ausencia de datos de otros tenants.

Documentación de Shopify:
- https://shopify.dev/docs/apps/build/marketing/build-web-pixels
- https://shopify.dev/docs/api/admin-graphql/latest/mutations/webPixelCreate
- https://shopify.dev/docs/api/web-pixels-api/standard-events
- https://shopify.dev/docs/api/web-pixels-api/pixel-privacy

**Release gate:** esta fase puede desplegarse sin efectos sobre datos de los compradores. No anuncia «Pixel conectado» en la UI ni autoriza disparar campañas o conversiones.
