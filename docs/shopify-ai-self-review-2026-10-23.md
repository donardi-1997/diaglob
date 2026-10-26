# DIAGLOB — Shopify App Store AI self-review (2026-10-23)

## Alcance y método

- Requisitos oficiales obtenidos en esta revisión con `shopify doc fetch --url https://shopify.dev/docs/apps/launch/app-store-review/app-store-ai-self-review-requirements`; copia de trabajo: `%TEMP%/diaglob-shopify-requirements-2026-10-23.md`. La fuente canónica enumera 100 IDs.
- Revisión estática del código y configuración local. No se consultó Shopify Partner ni una tienda, y no se verificaron despliegues, TLS en vivo, cargos o recorridos E2E; solo se ejecutaron las pruebas Shopify focalizadas indicadas abajo.
- **Revisión repetida tras `git pull`, checkout `f5631a4`:** requisitos oficiales descargados de nuevo y criterios reevaluados sobre la fuente actual. Pruebas Shopify enfocadas: backend instalación `2 passed`, backend checkout/draft `29 passed`, frontend instalación `9 passed`.
- El informe previo de 2026-10-20 se usó como antecedente, no como prueba de estado actual. Este documento incluye evidencia directa y líneas para cada criterio aplicable.
- No se modificaron producción, Shopify Partner ni los archivos existentes sin seguimiento. Solo se creó este informe.

## Resumen

✅ **Likely passing:** 22  
❌ **Likely failing:** 0  
⚠️ **Needs review:** 9  
⏭️ **Groups skipped:** 10

**Evaluación local:** los hallazgos de instalación manual de tienda (2.3.1) y registro de órdenes conversacionales fuera de checkout (1.1.2) aparecen corregidos en el código actualizado y sus pruebas Shopify específicas pasan. Aún quedan verificaciones de experiencia embebida, cobro real, TLS y listing que el código local no puede resolver por sí solo; completar esos pasos antes de marcar la lista de Partner como revisada.

**Nota:** Shopify volverá a revisar estos criterios y otros requisitos al recibir una solicitud. Los resultados “Likely passing” son indicios del código, no aprobación oficial.

## ✅ Likely passing

| ID | Criterio | Evidencia local |
|---|---|---|
| 1.1.2 | Use Shopify checkout | Se retiró la creación legacy de órdenes conversacionales COD: el helper rechaza la operación con `SHOPIFY_CHECKOUT_REQUIRED` ([shopify_cod_orders.py](../backend/app/shopify_cod_orders.py:29)). El checkout conversacional crea un draft y exige una `invoiceUrl` HTTPS del mismo dominio Shopify antes de mostrar el enlace de pago ([shopify_orders.py](../backend/app/shopify_orders.py:672), [conversational_checkout_service.py](../backend/app/services/conversational_checkout_service.py:738)). Las pruebas de checkout/draft pasaron (29); queda validar el flujo completo en una tienda.
| 1.1.3 | Direct merchants to the Shopify Theme Store | No se encontró extensión de tema ni flujo para instalar/descargar temas en la configuración Shopify revisada ([shopify.app.toml](../shopify.app.toml:1)). |
| 1.1.6 | Build single-merchant storefronts | Las operaciones se vinculan a tiendas DIAGLOB/Shopify identificadas; el código de fulfillment opera sobre órdenes de una tienda ([shopify_fulfillment.py](../backend/app/services/shopify_fulfillment.py:126)). La oferta a múltiples vendedores requeriría contexto externo no observado. |
| 1.1.7 | Build Payment Gateway apps using Payments API and authorization | No hay `write_payment_gateway` en los scopes declarados ([shopify.app.toml](../shopify.app.toml:10)); el código de cobros Shopify revisado es App Pricing ([shopify_hosted_plan_selection.py](../backend/app/services/shopify_hosted_plan_selection.py:74)), no un gateway de pagos. |
| 1.1.8 | Build apps for Shopify POS only | No se hallaron superficies POS externas en la integración Shopify revisada; la configuración declara una app embebida estándar ([shopify.app.toml](../shopify.app.toml:4)). |
| 1.1.10 | Maintain the cheapest shipping option as default | No se encontró extensión de checkout ni código Shopify que reordene opciones de envío; la integración de fulfillment crea envíos para órdenes existentes ([shopify_fulfillment.py](../backend/app/services/shopify_fulfillment.py:126)). |
| 1.1.14 | Don't connect merchants to external agencies and developers | No se encontró un flujo de contratación o directorio de agencias en la superficie Shopify; el App Home contiene enlaces de acceso/onboarding propios ([shopify_embedded.py](../backend/app/api/shopify_embedded.py:65)). |
| 1.1.15 | Process refunds only through the original payment processor | No se detectó función Shopify para emitir reembolsos en los módulos Shopify revisados; las mutaciones presentes incluyen creación de órdenes/fulfillment ([shopify_client.py](../backend/app/shopify_client.py:202), [shopify_fulfillment.py](../backend/app/services/shopify_fulfillment.py:56)). |
| 1.1.16 | Don't provide capital lending | No se detectó flujo de préstamos o adelantos en la superficie Shopify revisada; configuración y módulos de integración se identifican en [shopify.app.toml](../shopify.app.toml:1) y [backend/app](../backend/app/shopify_oauth.py:11). |
| 2.2.1 | Use Shopify APIs | Existe cliente Shopify Admin GraphQL y consultas/mutaciones ([shopify_client.py](../backend/app/shopify_client.py:16), [shopify_client.py](../backend/app/shopify_client.py:202)). |
| 2.2.3 | Use the latest version of Shopify App Bridge | App Home carga el script oficial de App Bridge ([shopify_embedded.py](../backend/app/api/shopify_embedded.py:51)); tokens ID se envían en `Authorization` y se verifican en las rutas protegidas ([shopify_embedded.py](../backend/app/api/shopify_embedded.py:376), [shopify_embedded.py](../backend/app/api/shopify_embedded.py:400)). |
| 2.2.4 | Use the GraphQL Admin API | El cliente construye la ruta `/admin/api/{version}/graphql.json` y envía GraphQL ([shopify_client.py](../backend/app/shopify_client.py:40), [shopify_client.py](../backend/app/shopify_client.py:65)). No se encontraron llamadas REST Admin generales en el código Shopify inspeccionado; los endpoints OAuth no son Admin REST de recursos. |
| 2.2.6 | Don't display promotions or advertisements in admin extensions | No hay extensiones de administración declaradas o archivos `shopify.extension.toml`; [shopify.app.toml](../shopify.app.toml:1) configura solo la app. |
| 2.2.7 | Only launch Max modal with merchant interaction | No hay extensión de Admin UI ni llamadas ResourcePicker/Max modal en la superficie Shopify inspeccionada; [shopify.app.toml](../shopify.app.toml:1). |
| 2.3.1 | Initiate installation from a Shopify-owned surface | El endpoint legado de conexión manual está retirado y devuelve `410 SHOPIFY_MANAGED_INSTALL_REQUIRED`, con instrucción para abrir la app desde Shopify Admin ([shopify.py](../backend/app/api/shopify.py:297), [shopify.py](../backend/app/api/shopify.py:303)). La edición general de tiendas ya no solicita el dominio Shopify; las pruebas dedicadas cubren ambas condiciones ([shopify-install.test.ts](../frontend/tests/shopify-install.test.ts:110)). Backend: `tests/test_shopify_owned_install_route.py` (2 passed); frontend: `shopify-install.test.ts` (9 passed).
| 2.3.2 | Authenticate immediately after install | El servidor construye la URL Shopify OAuth `/admin/oauth/authorize` ([shopify_oauth.py](../backend/app/shopify_oauth.py:95), [shopify_oauth.py](../backend/app/shopify_oauth.py:119)); el callback valida y procesa el intercambio ([shopify.py](../backend/app/api/shopify.py:336)). |
| 2.3.3 | Redirect to the app UI after installation | Tras procesar el callback el handler responde con redirección ([shopify.py](../backend/app/api/shopify.py:373), [shopify.py](../backend/app/api/shopify.py:376)); los destinos de instalación apuntan a la UI DIAGLOB ([shopify_public_install.py](../backend/app/services/shopify_public_install.py:64)). |
| 3.2.1 | Request read_all_orders only if necessary | El scope no aparece en los scopes fuente; la lista está definida explícitamente ([shopify_oauth.py](../backend/app/shopify_oauth.py:11), [shopify.app.toml](../shopify.app.toml:10)). |
| 3.2.2 | Request write_payment_mandate only if necessary | El scope no aparece en la lista OAuth ni en TOML ([shopify_oauth.py](../backend/app/shopify_oauth.py:11), [shopify.app.toml](../shopify.app.toml:10)). |
| 3.2.3 | Request write_checkout_extensions_apis only if necessary | El scope no aparece en la lista OAuth ni en TOML ([shopify_oauth.py](../backend/app/shopify_oauth.py:11), [shopify.app.toml](../shopify.app.toml:10)). |
| 3.2.4 | Request read_advanced_dom_pixel_events only if necessary | El scope no aparece en la lista OAuth ni en TOML ([shopify_oauth.py](../backend/app/shopify_oauth.py:11), [shopify.app.toml](../shopify.app.toml:10)). |
| 3.2.5 | Request read_checkout_extensions_chat only when required | El scope no aparece en la lista OAuth ni en TOML ([shopify_oauth.py](../backend/app/shopify_oauth.py:11), [shopify.app.toml](../shopify.app.toml:10)). |

## ❌ Likely failing

| ID | Criterio | Hallazgo y evidencia |
|---|---|---|

## ⚠️ Needs review

| ID | Criterio | Qué se detectó y qué falta confirmar |
|---|---|---|
| 1.1.1 | Use session tokens for authentication | El App Home carga App Bridge y las rutas protegidas validan ID tokens ([shopify_embedded.py](../backend/app/api/shopify_embedded.py:51), [shopify_embedded.py](../backend/app/api/shopify_embedded.py:400)). También hay un paso que abre DIAGLOB fuera del iframe para autenticación/código ([shopify_embedded.py](../backend/app/api/shopify_embedded.py:65), [ShopifyInstallPage.tsx](../frontend/src/pages/ShopifyInstallPage.tsx:218)). Verificar instalación nueva en Chrome incógnito, cookies de terceros bloqueadas y expiración de sesión. `localStorage` en la aplicación principal almacena preferencias/selección; se requiere probar que no actúa como sesión Shopify. |
| 1.1.4 | Use only factual information | El código obtiene datos de tienda/órdenes de Shopify ([shopify_client.py](../backend/app/shopify_client.py:16)); la descripción pública, claims, capturas y cualquier notificación de compra no están verificados en los archivos fuente. Confirmar que listing y UI no presentan ventas, reseñas o estadísticas simuladas como reales. |
| 1.1.9 | Obtain explicit buyer consent before adding charges | No se encontró extensión de checkout en la configuración. Las órdenes COD pueden incluir importes enviados en la creación de orden ([shopify_cod_orders.py](../backend/app/shopify_cod_orders.py:191)); falta confirmar si el flujo agrega cargos opcionales o modifica el total y, de hacerlo, cómo obtiene consentimiento del comprador. |
| 1.1.13 | Duplicate only authorized product information | DIAGLOB integra productos y proveedores; el código de sincronización importa datos de producto ([shopify.py](../backend/app/api/shopify.py:498)). Revisar lenguaje de marketing y salvaguardas que limiten copias a productos propios, licenciados o con derechos de reventa. |
| 1.2.1 | Use Shopify App Pricing or Shopify Billing API | Se genera enlace a planes alojados por Shopify ([shopify_hosted_plan_selection.py](../backend/app/services/shopify_hosted_plan_selection.py:74)); también existe integración Paddle para organizaciones/plataformas distintas ([shopify_app_pricing.py](../backend/app/services/shopify_app_pricing.py:5)). Verificar en Partner y en E2E que los comerciantes Shopify solo pagan mediante Shopify App Pricing/Billing y que ninguna UI Shopify deriva a Paddle. |
| 1.2.2 | Implement App Pricing/Billing correctly | La integración trata selección alojada y verificación de suscripción ([shopify_hosted_plan_selection.py](../backend/app/services/shopify_hosted_plan_selection.py:74), [shopify_app_pricing.py](../backend/app/services/shopify_app_pricing.py:263)). Falta evidencia de aceptación, rechazo, reintento tras reinstalación y comportamiento real de cargos en la cuenta Partner. |
| 1.2.3 | Allow pricing plan changes | Existe navegación al área de precios de Shopify ([shopify_hosted_plan_selection.py](../backend/app/services/shopify_hosted_plan_selection.py:74)); confirmar con merchant E2E que upgrade/downgrade se completa sin soporte ni reinstalación y aparece en el historial de cargos. |
| 2.3.4 | Require OAuth immediately after reinstall | El callback procesa OAuth ([shopify.py](../backend/app/api/shopify.py:336)); hay lógica de recuperación/instalación administrada con token exchange y grant pendiente ([shopify_managed_installation.py](../backend/app/services/shopify_managed_installation.py:130)). Probar reinstalación de una tienda existente y confirmar actualización/reautorización sin bloqueo por identidad o registro duplicado. |
| 3.1.1 | Use a valid TLS/SSL certificate | TOML y URLs del servicio usan HTTPS ([shopify.app.toml](../shopify.app.toml:6), [shopify.app.toml](../shopify.app.toml:16)), pero esto no demuestra certificado vigente ni ausencia de errores en todos los hosts. Verificar TLS del dominio productivo, cadena, expiración y redirección HTTP→HTTPS desde fuera del código. |

## ⏭️ Skipped groups

| Grupo | Razón |
|---|---|
| 5.1 Online store | Condicional: no se encontró `shopify.extension.toml` con `type = "theme"`. |
| 5.2 Payment | Condicional: no hay extensión `type = "payment"` ni scope `write_payment_gateway`. |
| 5.3 Payment facilitator | Opt-in; no solicitado. |
| 5.4 Purchase option | Condicional: TOML no solicita scopes de customer payment methods, own subscription contracts ni payment mandate. |
| 5.5 Product sourcing | Opt-in; no solicitado. |
| 5.6 Checkout customization | Condicional: no se detectó extensión `type = "ui-extension"` con targets checkout. |
| 5.7 Sales channel | Condicional: no se detectó extensión `type = "channel_config"`. |
| 5.8 Post purchase | Condicional: no se detectó extensión `type = "checkout_post_purchase"`. |
| 5.9 Mobile app builders | Opt-in; no solicitado. |
| 5.10 Donation | Opt-in; no solicitado. |

## Límites y referencias

Esta revisión no pudo verificar el listing público, Partner Dashboard, estado de aprobación de protected customer data, permisos efectivos, certificados TLS en vivo, recibos/cargos, entrega de webhooks en producción ni el comportamiento de los flujos en una tienda. Las referencias locales son pruebas de fuente y pueden no coincidir con la versión desplegada.

- [App Store requirements documentation](https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements)
- [Best practices for apps](https://shopify.dev/docs/apps/launch/shopify-app-store/best-practices)
- [About billing for your app](https://shopify.dev/docs/apps/launch/billing)
- [Submitting your app for review](https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review)
