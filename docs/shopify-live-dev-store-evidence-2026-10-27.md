# DIAGLOB — Evidencia en tienda de desarrollo para Shopify App Store

**Fecha:** 2026-10-27
**Tienda:** diaglob-poc.myshopify.com (Development store, DIAGLOB org)
**Alcance:** comprobaciones de solo lectura más cambios de planes Shopify gratuitos, autorizados por el usuario. No hubo cargos, reinstalación ni cambios en producción o Partner.

Este addendum complementa [el informe de cierre anterior](shopify-review-closure-2026-10-27.md) sin reemplazarlo.

## Resultados de los cinco criterios pendientes

| Criterio | Resultado | Evidencia y alcance |
|---|---|---|
| **1.1.4 — Información factual** | **Needs review** | El App Home de la tienda mostró Diaglob Colombia, diaglob-poc.myshopify.com, país CO, moneda COP, acceso de solo lectura, 6 productos guardados, 1 pedido registrado y la advertencia “Las cifras no son consultas en tiempo real a Shopify”. No obstante, la publicación en Partner seguía Enviado; la página informó que el contenido no se podía editar durante la revisión. No fue posible cotejar descripción, imágenes y screencast publicados. Superficies observadas: Admin /store/diaglob-poc/apps/diaglob; Partner /5148778/apps/416524435457/distribution/app-store. |
| **1.2.1 — Shopify App Pricing / Billing API** | **Needs review** | La suscripción de esta instalación se gestionó íntegramente desde Shopify Admin. En planes públicos, Shopify mostró Starter ($190/año), Growth ($490/año) y Pro ($990/año), todos con $0 durante la prueba en esta tienda de desarrollo; la confirmación indicó que no habría cargo. Esto prueba el flujo de esta instalación, pero no determina si Paddle se ofrece a comerciantes Shopify por otra ruta comercial. El informe anterior enlaza las guardas de facturación locales en backend/app/api/billing.py y la selección Shopify alojada. Superficies observadas: /store/diaglob-poc/charges/diaglob/pricing_plans y /store/diaglob-poc/settings/apps/app_installations/app/diaglob. |
| **1.2.3 — Cambios de plan** | **Likely passing (prueba funcional en tienda)** | Sin desinstalar ni reinstalar: se cambió Starter público a Growth anual y se aprobó la pantalla “Gratis para probar / No se te cobrará”; Shopify volvió a la App Home normal. Luego se cambió de Growth a Starter público anual con la misma confirmación gratuita; Shopify volvió a la App Home y cargó los módulos, y Admin confirmó Prueba gratis, Starter, $0/año después de la prueba. La aplicación conservó la conexión y sus módulos de Resumen, Productos y Pedidos. El historial de facturación de la organización estuvo disponible en /store/diaglob-poc/settings/organization-billing y mostró dos facturas anteriores por $0,00; la tienda de desarrollo no produjo una factura de cargo para estas pruebas gratuitas, así que esto no acredita un ciclo pagado real. |
| **5.5.1 — Fulfillment de product sourcing** | **No aplicable al alcance declarado actualmente** | Partner, Distribución, sección Criterios específicos por categoría, indicó literalmente: “Shopify no ha asignado tu app a ninguna categoría específica”. En la instalación observada, DIAGLOB muestra sincronización de catálogo y pedidos con acceso de solo lectura; no ofrece un flujo de sourcing/fulfillment. No se cambiaron la categoría ni los permisos. Revaluar si se declara Product Sourcing o se agrega esa funcionalidad. |
| **5.5.2 — COGS de product sourcing** | **No aplicable al alcance declarado actualmente** | La misma pantalla de Partner indicó que no hay categoría específica asignada; el App Home no ofrece una función para escribir COGS en productos. Revaluar si se declara Product Sourcing o se agrega escritura de costos. |

## Anomalía limitada a plan privado de prueba

Al restaurar el estado inicial se probó brevemente el plan privado de $0 creado para E2E (Free private plan for E2E testing on the Diaglob development store). Ese callback abrió /store/diaglob-poc/apps/diaglob/app/plans?plan_handle=diaglob-poc-test... y el iframe mostró que api.diaglob.tech rechazó la conexión. Se restauró luego el plan público Starter mediante Shopify App Pricing; el callback público /apps/diaglob/api/shopify/embedded?...&plan_handle=starter volvió a cargar normalmente. El plan privado de desarrollo no es uno de los planes comerciales públicos.

## Estado final de la tienda

- App DIAGLOB sigue instalada y conectada en diaglob-poc.myshopify.com.
- Plan público Starter anual en prueba; Admin muestra $0/año después de la prueba y tres días restantes.
- Sin cargos: las confirmaciones de ambos planes indicaron que no se facturarían.
- La revisión de Partner permanece Enviado; no se retiró ni editó.
- No se ejecutó ningún fulfillment, escritura de COGS ni acción en producción.

## Acceso que falta para los dos criterios abiertos

1. **1.1.4:** acceso de lectura a la publicación enviada (copy, medios y screencast) después de que Shopify libere la edición o acceso del propietario a la vista previa de esa publicación.
2. **1.2.1:** confirmación verificable del flujo comercial directo que usa Paddle y sus destinatarios; una tienda de desarrollo instalada mediante Shopify no permite acreditar si se factura externamente a otros comerciantes Shopify.
