# Shopify Web Pixel — Fase 2, incorporación controlada (2026-10-11)

## Ya implementado en Diaglob

- SDK Web Pixels con transformaciones para `page_viewed`, `product_viewed`, `product_added_to_cart`, `checkout_started`, `checkout_completed`.
- `event.id` estable prefijado `shopify:` para eventual deduplicación con Meta Conversions API; usa importes/monedas del propio evento, sin datos de identificación de clientes.
- Código en `shopify/web-pixel-staging/src/` y plantilla estricta de privacidad en `shopify.extension.toml.template`. **No hay UID inventado** ni extensión vinculada a la app Shopify.
- GraphQL `webPixelCreate`/`webPixelDelete` desde Diaglob, con validación de organización, asignación de tienda, Pixel existente, ausencia declarada de fuentes duplicadas, token OAuth con `write_pixels`/`read_customer_events`, y allowlist de dominios.
- Provisionar configura `trackingEnabled="false"`. NO publica eventos, no llama Conversions API y no inicia campañas.
- Tres rutas adicionales `GET .../meta-pixel/readiness`, `POST .../meta-pixel/provision`, `POST .../meta-pixel/unprovision`.
- Ninguna operación sobre tiendas reales sin habilitar explícitamente la función y la lista de tiendas autorizadas.

## Condiciones previas obligatorias

**La instalación de la extensión no está hecha en Shopify Partner.** El repositorio no contiene un proyecto CLI asociado a la app existente, así que todavía no puede generarse un UID legítimo ni comprobarse el despliegue remoto.

1. Desde un directorio local Shopify CLI, enlazar con la **app Diaglob existente**, no crear otra:

   `shopify app config link`

   Verificar visualmente el Client ID, la URL de callback y la versión de aplicación antes de aceptar cambios en la configuración.
2. Ejecutar:

   `shopify app generate extension --template web_pixel --name diaglob-meta-pixel`

   Seleccionar JavaScript. **Conservar el UID generado por Shopify** y no copiar una configuración falsa.
3. En la extensión generada, reemplazar `src/index.js` por `shopify/web-pixel-staging/src/index.js` y agregar `src/mapping.mjs` desde esta rama. Conservar el package.json generado y su dependencia `@shopify/web-pixels-extension`.
4. En `shopify.extension.toml` aplicar los campos de `shopify.extension.toml.template` manteniendo el UID; usar `runtime_context="strict"`, `customer_privacy.analytics=true`, `customer_privacy.marketing=true`, `customer_privacy.preferences=false` y `sale_of_data="enabled"`.
5. Solicitar y confirmar permisos `write_pixels` y `read_customer_events` en la configuración real. **No añadirlos unilateralmente al OAuth productivo** sin validar instalaciones y revisión de Shopify.
6. `shopify app config validate` y `shopify app deploy --no-release`, probar en dev store; liberar la versión tras aprobación de revisión y validación.
7. Solo para tienda `diaglob-poc.myshopify.com`, y **después** de desplegar la extensión, puede optarse explícitamente por permitir aprovisionamiento inerte configurando:
   - `META_WEB_PIXEL_SHOPIFY_PROVISION_ENABLED=true`
   - `META_WEB_PIXEL_EXTENSION_DEPLOYED=true`
   - `META_WEB_PIXEL_SHOP_ALLOWLIST=diaglob-poc.myshopify.com`

   El valor por defecto es FALSE y allowlist vacía. Con ellos solamente se crea el registro en Shopify, con `trackingEnabled=false`.
8. Verificar Shopify Admin → Settings → Customer events → App pixels. Debe figurar la app con extensión provisionada sin enviar eventos.

## Lo que TODAVÍA NO está implementado

**NO activar el envío de eventos en vivo ni anunciar Meta Pixel conectado**. El endpoint `https://api.diaglob.tech/api/web-pixels/collect` de la plantilla es una dirección prevista, no un colector habilitado. El Pixel la utiliza únicamente si una futura versión cambia explícitamente `trackingEnabled="true"`, cosa que este PR NO hace.

Faltan:
- Publicar un colector de eventos aislado por organización/tienda con límites de tasa, integridad de origen y protección ante eventos falsificados (un `sourceId` público no autentica los eventos ni es prueba de una compra).
- Desarrollar Conversions API por tienda con token cifrado propio, deduplicación `event_id`, límites y controles de privacidad/retención, revocación, y la verificación del propietario del Pixel; no reutilizar el Pixel de adquisición Diaglob.
- Evitar medición duplicada si el merchant usa la app Facebook & Instagram de Shopify.
- Aceptación de consentimiento en Shopify Customer Privacy y verificación en Meta Events Manager con Test Events.
- E2E en `diaglob-poc.myshopify.com`, incluyendo checkout de prueba, 2 tiendas/organizaciones, revocación de permisos e instalación/reinstalación.

No configurar cuentas de Meta Ads ni iniciar campañas o cargos. No tocar Bakatá.

## Referencias oficiales

- https://shopify.dev/docs/apps/build/marketing/build-web-pixels
- https://shopify.dev/docs/api/shopify-cli/app/app-config-link
- https://shopify.dev/docs/api/admin-graphql/2026-07/mutations/webPixelCreate
- https://shopify.dev/docs/api/web-pixels-api/standard-events
- https://shopify.dev/docs/apps/launch/privacy-requirements
