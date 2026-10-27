# Shopify App Pricing — corrección del retorno y cierre de criterios

**Fecha:** 2026-10-27
**App:** DIAGLOB, ID 416524435457
**Tienda de prueba:** diaglob-poc.myshopify.com
**Alcance:** cambio local y pruebas; no se desplegó producción ni se modificó Partner.

## Anomalía reproducida

La versión activa de Shopify configura la App Home en https://api.diaglob.tech/api/shopify/embedded. El plan privado E2E enviaba la aprobación a /app/plans en ese mismo host. Una solicitud HTTPS GET de solo lectura confirmó:

- https://api.diaglob.tech/app/plans → 404, X-Frame-Options: DENY.
- https://diaglob.tech/app/plans?plan_handle=... → 200 y carga el workspace de facturación.
- https://api.diaglob.tech/api/shopify/embedded → 200, CSP permite admin.shopify.com.

Shopify documenta que cada plan tiene su propio Welcome link y que plan_handle solo debe iniciar una verificación nueva de la suscripción ([Shopify App Pricing](https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing), [planes públicos y privados](https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/plans)). La pantalla pública de planes ya regresó a App Home durante las pruebas Starter → Growth → Starter; el fallo observado era la URL heredada del plan privado.

## Corrección local

- Se agregó GET /app/plans, que redirige a FRONTEND_URL/app/plans (por defecto https://diaglob.tech/app/plans) usando solo un marcador canónico plan_handle=shopify-hosted-return. No reenvía shop, charge_id ni parámetros arbitrarios.
- El destino frontend ya elimina plan_handle y shop y, si la organización es Shopify, vuelve a consultar la suscripción al Partner API: frontend/src/services/shopifyBillingReturn.ts:1 y frontend/src/pages/ShopifyBillingWorkspace.tsx:276.
- El redirect tiene CSP limitado a https://admin.shopify.com; otras rutas continúan con X-Frame-Options: DENY.
- No desplegué el cambio: el dominio API está conectado a la app activa y sigue vigente el límite de no cambiar producción. El GET público seguirá en 404 hasta publicar/desplegar la corrección o editar el Welcome link privado en Partner.

Código y pruebas:

- backend/app/api/shopify_embedded.py:29
- backend/app/services/shopify_navigation.py:11
- backend/app/runtime/security.py:11
- backend/tests/test_shopify_pricing_welcome_navigation.py:36
- backend/tests/test_shopify_pricing_welcome_navigation.py:77

## Estado de los cinco criterios

| Criterio | Estado | Base |
|---|---|---|
| **1.1.4 — Información factual** | **Needs review** | Admin muestra datos de la tienda y la nota de no tiempo real, pero Partner aún tiene el envío Enviado y bloquea la edición; falta cotejar copy, imágenes y screencast del listing. |
| **1.2.1 — Shopify App Pricing / Billing API** | **Needs review** | La tienda instaló y aprobó planes en Shopify Admin. El canal shopify_install bloquea operaciones Paddle incluso si el proveedor quedó inconsistente; ver backend/app/api/billing.py:112 y backend/tests/test_shopify_billing_channel_guard.py:40. El código conserva Paddle para altas directas que luego conectan una tienda Shopify; falta confirmar que ese flujo no sea una vía de adquisición de la misma app para comerciantes App Store. |
| **1.2.3 — Cambios de plan** | **Likely passing en el código local; smoke test del callback corregido pendiente de despliegue** | Los planes públicos Starter → Growth → Starter se aprobaron sin reinstalar ni contactar soporte; Shopify regresó a App Home y Admin confirmó Starter. La ruta heredada del plan privado ahora entrega el retorno al workspace, donde se revalida contra Shopify. La prueba local verifica destino fijo, sanitización, retorno HTTP y CSP. |
| **5.5.1 — Fulfillment de product sourcing** | **No aplicable al alcance actual** | Partner muestra “Shopify no ha asignado tu app a ninguna categoría específica”. La app observada solo presenta datos de catálogo/pedidos en modo de lectura; no ofrece sourcing/fulfillment. |
| **5.5.2 — COGS de product sourcing** | **No aplicable al alcance actual** | La app no ofrece escritura de COGS y Partner no tiene categoría específica asignada. |

El estado No aplicable para 5.5.1/5.5.2 debe revisarse si se asigna Product Sourcing o se agrega esa función.

## Verificación ejecutada

- Pruebas nuevas de retorno, destino seguro, sanitización y origen inválido, navegación Shopify y guardas de canal: **28 passed, 1 warning**.
- App Pricing, transiciones y recuperación de reautorización: **113 passed, 459 warnings**.
- git diff --check: sin errores.
- No se validó el callback corregido contra api.diaglob.tech porque el código no se desplegó.

## Pendiente restante

Para cerrar 1.1.4 falta revisar la publicación enviada (descripción, medios y screencast) cuando Shopify permita verla/editarla durante o después de la revisión. Para cerrar 1.2.1 falta confirmar el alcance comercial de las altas directas Paddle con conexión Shopify. Para verificar la corrección de 1.2.3 en la tienda real hace falta desplegar este cambio o actualizar solo el Welcome link del plan privado; esta pasada no hizo ninguna modificación externa.
