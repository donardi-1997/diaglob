# Shopify: revisión y correcciones — 2026-10-26

> **Resultado: NO LISTA PARA ENVÍO (fase 3).** Se corrigieron brechas locales de checkout, validación, retorno embedded, privacidad local con ejecución real deshabilitada por defecto, y se cerró la brecha local de privacidad integral (inventario por tienda, manifiesto de subprocesadores y drills de restauración). Se obtuvieron evidencias reales de Shopify Partners, Dev Dashboard y Shopify Admin. Persisten bloqueos externos: verificación independiente de controles, aprobación PCD, E2E de instalación/reinstalación y facturación. Una configuración válida o pruebas correctas no equivalen a aprobación de Shopify.

## Alcance y fuente oficial

- Proyecto: `C:\Users\adria\OneDrive\Documentos\diaglob`; base `3930472` más los cambios locales de esta revisión, todavía sin commit.
- Shopify CLI **4.9.4** descargó los requisitos vigentes con autorización del usuario:

  ```text
  shopify doc fetch --url https://shopify.dev/docs/apps/launch/app-store-review/app-store-ai-self-review-requirements --output C:\Users\adria\AppData\Local\Temp\opencode\diaglob-shopify-requirements-2026-10-26.md
  shopify app config validate --json
  ```

- Se leyó el documento completo: **100 requisitos**, de los cuales **31** corresponden a los grupos generales evaluados y **69** pertenecen a los diez grupos omitidos por las reglas de aplicabilidad/opt-in.
- SHA-256 de esa descarga: `8344cf11677e42569e83f4ca5c94317ead3abaece18ab3aae21c0f6cfc5488d0`.
- La validación CLI devolvió `{"valid":true,"issues":[]}`. Es validación del esquema local, **no** confirmación de versión activa, distribución, scopes concedidos ni aprobación PCD.
- Se revisaron código, configuración, pruebas e informes anteriores. Solo se hicieron comprobaciones públicas anónimas adicionales; no se accedió a Partner ni a sesiones/datos de comerciantes.
- **No hubo commit, push, publicación, despliegue, instalación, cambio de permisos instalados, cargo, devolución ni borrado real.** No se modificaron modelos ni migraciones.

## Correcciones implementadas

| Hallazgo | Corrección local | Evidencia |
| --- | --- | --- |
| Las rutas generales Nequi/Mercado Pago podían cobrar compras Shopify aunque el checkout conversacional ya estuviera protegido. | `payment_service.py` comprueba procedencia al descubrir proveedores, configurar conexiones, crear pagos y antes de ejecutar un pago todavía no enviado al proveedor. Las rutas de configuración/creación devuelven **409 `SHOPIFY_CHECKOUT_REQUIRED`**; la lista de proveedores vacía oculta los paneles existentes. | [Servicio](../backend/app/services/payment_service.py), [rutas](../backend/app/api/payments.py), [regresiones](../backend/tests/test_payments.py). |
| Desconectar Shopify o perder una referencia no debía habilitar checkout externo. | La protección considera conexiones históricas de la tienda, dominio Shopify heredado, origen `shopify`/`shopify_*` e IDs de pedido/draft. También se aplica a organizaciones con proveedor Shopify u origen `shopify_install`, aunque el otro indicador sea inconsistente. | Casos de conexión conectada/desconectada/revocada/error, procedencia organizacional y pedidos sin conexión. |
| El endpoint PoC estaba retirado, pero su helper interno todavía implementaba `orderCreate`. | Se retiró también la implementación del helper: siempre rechaza con `SHOPIFY_CHECKOUT_REQUIRED`, como el helper COD. El servicio no puede reactivar esa vía. | [Helper PoC](../backend/app/shopify_poc.py), [pruebas de helper/servicio/ruta](../backend/tests/test_shopify.py). |
| El preflight comparaba el client ID del TOML consigo mismo; otra app con un ID bien formado podía pasar. | Se contrasta con la identidad pública DIAGLOB, compartida con App Home. También se detecta divergencia entre la versión de webhooks y la versión del cliente Admin GraphQL. | [Preflight](../backend/tools/shopify_review_source_preflight.py), [identidad compartida](../backend/app/shopify_app_config_audit.py), [pruebas](../backend/tests/test_shopify_review_source_preflight.py). |
| Un cambio solo en configuración Shopify podía saltarse validaciones del PR; faltaba un paso explícito de preflight antes del despliegue. | Los cambios en `shopify.app.toml`/`shopify/*` activan backend y frontend. El preflight de solo lectura corre en PR y en el job `validate` de producción; se conserva `deploy.needs: validate`. | [PR](../.github/workflows/validate-pr.yml), [producción](../.github/workflows/deploy-production.yml), [regresiones CI](../backend/tests/test_shopify_review_ci_gate.py). |
| El bootstrap de secretos fallaba en Windows por ausencia de `os.fchmod`; la prueba de symlink necesitaba privilegios del sistema. | Si no hay permisos seguros por descriptor, se rechaza la creación **antes de generar o escribir el secreto**. No se sustituye por un `chmod` que no proteja ACL. La prueba del rechazo de symlink sigue ejecutando sus aserciones sin exigir elevación. | [Bootstrap](../scripts/shopify_privacy_review_secret.py), [pruebas](../backend/tests/test_shopify_privacy_review_secret_bootstrap.py). |

**Compatibilidad:** no se bloquean los pagos de otra tienda independiente en una organización de origen directo solo porque una tienda distinta conectó Shopify. En organizaciones adquiridas por Shopify, la restricción es deliberadamente organizacional. Las devoluciones históricas siguen usando su procesador y referencia originales; no se reemplazan por saldo, gift cards u otro proveedor. Reconciliar/cancelar/devolver operaciones históricas no constituye una nueva autorización para cobrar.

## Fase 2 — evidencias de Shopify y correcciones adicionales (2026-10-26)

### Evidencias obtenidas en Shopify (solo lectura salvo PCD)

| Elemento | Estado verificado |
| --- | --- |
| Aplicación | Partner org **5148778**, app **416524435457**, client ID `c5fc9aed710462d41767477fa9e595c0`. |
| Versión activa | **`diaglob-scopes-1`**, ID `1174672506881`, lanzada 20-10-2026 desde `a52238d`; App Home embedded en `https://api.diaglob.tech/api/shopify/embedded`, callback `https://api.diaglob.tech/api/shopify/callback`, API `2026-07`. |
| Scopes activos | Los **siete** scopes del TOML local, coincidentes: `read_products,read_inventory,read_orders,write_orders,write_draft_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders`. Sin `read_customers`. |
| Webhooks activos | Los tres de cumplimiento (`customers/data_request`, `customers/redact`, `shop/redact`) apuntan a `/api/webhooks/shopify/compliance`. |
| Encuesta PCD | Borrador: `PROTECTED_CUSTOMER_DATA` + `NAME/EMAIL/PHONE/ADDRESS` en estado `REQUESTED`, motivos `STORE_MANAGEMENT` + `APP_FUNCTIONALITY`. **No hace falta volver a solicitarlos.** La app figura **no aprobada** para PCD; Shopify revisará al enviar la publicación. |
| Detalles de protección de datos | **16/16 preguntas en «Sí»** tras adoptar el titular la política de incidentes y guardar solo esa respuesta (autorización explícita del titular). Las otras quince respuestas preexistentes **no fueron verificadas operativamente** por esta revisión. |
| Tienda de desarrollo | `diaglob-poc.myshopify.com` (org dev 233061035, store 76901810367), tipo **En desarrollo**, plan mostrado **Basic**. La app aparece instalada y su App Home abre dentro del Admin. |
| Listing | Tres planes públicos (`starter` $19/$190, `growth` $49/$490, `pro` $99/$990, trial 3 días) y dos privados; categoría Analytics; screencast público `https://youtu.be/6zdgFoCWVXs` («Diaglob Shopify Review»). |
| Aviso Dev Dashboard | **«Token offline obsoleto — Corrección vencida»**, última detección 20-10-2026. El árbol local ya usa tokens offline expirables (`expiring=1`) con rotación de refresh tokens y validación de scopes en el refresco; el aviso corresponde a credenciales de instalaciones previas al canje expirable y debe resolverse con despliegue/reinstalación autorizados, no en el dashboard. |

**Límites de estas evidencias:** corresponden al estado observado el 26-10-2026. No acreditan aprobación, funcionamiento de los planes, flujo del reviewer ni despliegue de este árbol. No se aceptó ni rechazó ningún plan, no se instaló/reinstaló y no se modificó el listing.

### Correcciones locales añadidas en fase 2

| Hallazgo | Corrección local | Evidencia |
| --- | --- | --- |
| El CSP de App Home permitía enmarcar desde cualquier `*.myshopify.com`. | CSP dinámica: `frame-ancestors https://admin.shopify.com` más un único dominio canónico validado del parámetro `shop`; sin comodín. El hint de framing **nunca** autentica tienda ni usuario. | [Seguridad](../backend/app/runtime/security.py), regresiones parametrizadas en [embedded entry](../backend/tests/test_shopify_embedded_entry.py). |
| Tras conectar la cuenta no había retorno seguro a App Home. | `shopify_app_home_url()` devuelve el enlace canónico del shop verificado a `/admin/apps/<client_id>`; el frontend valida el resultado del claim (conectado, store, shop y URL exactos) y muestra pantalla de éxito con generación explícita de código de vinculación. | [Navegación](../backend/app/services/shopify_navigation.py), [pantalla](../frontend/src/pages/ShopifyInstallPage.tsx), [pruebas backend](../backend/tests/test_shopify_navigation.py) y [frontend](../frontend/tests/shopify-install.test.ts). |
| El claim no persistía el dominio Shopify verificado en la tienda. | `claim_install()` guarda `store.shopify_domain` con el grant verificado. | [Instalación](../backend/app/services/shopify_public_install.py). |
| La redacción local solo existía como manifiesto; la entrega era sintética. | Ejecución local real (exportación parcial cifrada de un solo uso ligada al destinatario, y redacción atómica con tombstones y checkpoint de recuperación) **deshabilitada por defecto**: exige política adoptada por hash, permiso Ed25519 firmado externamente por caso/alcance/operación, checkpoint de restauración anclado externamente y bloqueo por tienda. Nunca marca `fulfillment_complete=true`. | [Autorización](../backend/app/services/shopify_privacy_execution_authorization.py), [ejecución](../backend/app/services/shopify_privacy_local_execution.py), [entrega](../backend/app/services/shopify_privacy_live_delivery.py), [política](../config/shopify-privacy-policy.json), [pruebas](../backend/tests/test_shopify_privacy_local_execution.py). |
| La política de privacidad/retención y la de incidentes no existían como documentos adoptables. | Redactadas y **adoptadas por el titular** como base operativa (no como dictamen jurídico ni certificación): [retención](legal/shopify-privacy-retention-policy.md) e [incidentes](legal/security-incident-response-policy.md). El archivo JSON fija parámetros reproducibles y su hash actúa como ancla de adopción. | Documentos legales y configuración. |

## Fase 3 — cobertura integral de privacidad local (2026-10-26)

Cierra la brecha **local** del bloqueo P0 de privacidad integral: las seis superficies de datos ahora tienen inventario efectivo por tienda, manifiesto completo de subprocesadores con confirmación de encargados por control, y mecanismo de drill de restauración con ledger externo. Todo sigue **fail-closed**: ningún módulo autoriza exportación, borrado o entrega real, ninguna solicitud se marca completa y ningún control se da por verificado.

| Brecha del bloqueo P0 | Implementación local | Evidencia |
| --- | --- | --- |
| Inventario efectivo por tienda | `build_shopify_privacy_shop_inventory` exige intake firmado y shop verificado, y agrega por tienda: registros estructurados (preview de ámbito con clientes compartidos protegidos), IA/Copilot (conteos store-wide sin leer contenido), atribución legacy de IA, superficies knowledge/archivos, automatizaciones con linaje fail-closed, procesadores activos y superficies de backup. Solo conteos, etiquetas de cobertura y bloqueadores; cero PII. | [Servicio](../backend/app/services/shopify_privacy_shop_inventory.py), endpoint `GET /api/internal/shopify/privacy/cases/{request_id}/shop-inventory`, [pruebas](../backend/tests/test_shopify_privacy_shop_inventory.py). |
| IA y contenido no estructurado / archivos | Recuento de knowledge bases por alcance (organización vs seleccionadas por tienda) y knowledge sources visibles, con `content_read=False`, `object_keys_read=False` y `export_verified=False`; hereda los contadores Copilot y el preflight de atribución legacy con sus bloqueadores intactos. | [Inventario](../backend/app/services/shopify_privacy_shop_inventory.py), [pruebas](../backend/tests/test_shopify_privacy_shop_inventory.py). |
| Procesadores externos y confirmación de encargados | Manifiesto de **16 subprocesadores** (Shopify, Nuvemshop, Dropi, CJ, Meta Ads, Google, WhatsApp, Telegram, Instagram, email, Mercado Pago, Nequi, Paddle, Bedrock, S3, transportistas) en **bijección exacta** con `PROCESSOR_CONTROLS` (ampliado de 8 a 16): cada procesador es ahora confirmable con evidencia digest. Activación detectada solo por conteo de filas por tienda/organización (`connected`, `present_unverified`, `not_detected` o `manual_confirmation_required`); toda entrada queda `unverified` con `independently_verified=False`. | [Manifiesto](../backend/app/services/shopify_privacy_subprocessors.py), [controles](../backend/app/services/shopify_privacy_controls.py), endpoint `GET .../cases/{request_id}/subprocessors`, [pruebas](../backend/tests/test_shopify_privacy_subprocessors.py). |
| Backups y drills de restauración con ledger externo | `inspect_shopify_privacy_backup_coverage` (las seis superficies `RESTORE_CONTROLS` por tienda, filas del ledger de supresiones, ancla offsite obligatoria) y `run_shopify_privacy_restore_drill` (reconciliación contra el HMAC pre-restore guardado fuera; origen del ancla declarado `caller_attested_not_independently_verifiable`). Un drill aprobado **no** eleva `restore_verified`, `backup_erasure_verified` ni `fulfillment_complete`. | [Backups](../backend/app/services/shopify_privacy_backup_coverage.py), endpoint `POST /api/internal/shopify/privacy/restore-drill`, [pruebas](../backend/tests/test_shopify_privacy_backup_coverage.py). |

**Lo que esta fase NO cierra (sigue bloqueado a propósito):** verificación independiente de cada control; aprobación legal del calendario de retención y legal holds; existencia, caducidad y reconciliación de los backups reales (viven fuera de la aplicación); borrado verificado en procesadores externos; activación de la ejecución real (deshabilitada por defecto por política + permiso firmado); y la aprobación PCD. Los bloqueadores `RECORD_PROVENANCE_INCOMPLETE`, `UNSTRUCTURED_SUBJECT_LINKAGE_UNVERIFIED`, `QUEUED_PAYLOAD_COVERAGE_UNVERIFIED`, `EXTERNAL_PROCESSOR_COVERAGE_UNVERIFIED`, `LEGAL_RETENTION_POLICY_NOT_APPROVED` y `BACKUP_RESTORE_COVERAGE_UNVERIFIED` **permanecen** en todo resultado.

## Resumen base de 31 requisitos generales (complementado por autoevaluación vigente)

Este resumen conserva el primer pase de criterios generales. La revisión posterior está en [AI self-review vigente](shopify-app-store-ai-review-2026-10-26.md): añadió los tres requisitos del grupo **5.5 Product sourcing**, aplicable porque Partner muestra esa capacidad, y actualizó el resultado agregado a **24 likely passing, 2 likely failing, 8 needs review y 66 omitidos**. Para el estado actual debe prevalecer ese addendum.

- ✅ **Likely passing: 23**.
- ❌ **Likely failing: 0** entre estos 31 criterios, después de las correcciones.
- ⚠️ **Needs review: 8**.
- ⏭️ **Groups skipped: 10**; 69 requisitos no evaluados.

**Importante:** este subconjunto canónico no incluye todas las obligaciones de privacidad, PCD, listing y operación. Los bloqueos de la sección siguiente mantienen el **NO-GO**, aunque aquí no haya un criterio clasificado como fallo confirmado. Shopify revisará este subconjunto y requisitos adicionales al recibir la solicitud.

### ⚠️ Requisitos que necesitan revisión

| ID / requisito | Qué se detectó | Por qué requiere atención / cierre necesario |
| --- | --- | --- |
| **1.1.1 — Use session tokens for authentication** | App Home carga App Bridge y usa `shopify.idToken()` con autorización por miembro/tienda. El primer onboarding requiere otra pestaña y códigos explícitos. | Ejecutar Chrome incógnito con cookies de terceros bloqueadas, usuario nuevo/staff, expiración de sesión y recarga. No confundir un ID token válido con autorización a un tenant DIAGLOB. [App Home](../backend/app/api/shopify_embedded.py), [vinculación](../backend/app/services/shopify_embedded_membership.py). |
| **1.1.4 — Use only factual information** | Las métricas incrustadas consultan registros reales y explican que no son datos en tiempo real. No se detectaron ventas/reseñas ficticias en esa superficie. | Revisar texto, capturas y screencast reales del listing; la fuente local no acredita lo publicado. No presentar fixtures ni gráficos promocionales como pruebas de funcionamiento. |
| **1.1.13 — Duplicate only authorized product information** | Hay sincronización de catálogo y conexiones con proveedores. | Confirmar derechos del comerciante/proveedor y que el marketing no ofrezca copiar cualquier tienda o sitio. La existencia de una conexión no demuestra licencias de terceros. [Sincronización](../backend/app/shopify_sync.py). |
| **1.2.1 — Use Shopify App Pricing or the Shopify Billing API** | Hay selección alojada de planes y guardas contra Paddle para organizaciones Shopify/origen Shopify. También existe el canal Paddle legítimo para altas directas. | Comprobar procedencia real y planes de cada recorrido de adquisición. No declarar gratis una app que cobra al merchant fuera de Shopify; no inferir una excepción de billing por tener un conector. [Guarda](../backend/app/api/billing.py), [selección de planes](../backend/app/services/shopify_hosted_plan_selection.py). |
| **1.2.2 — Implement Shopify App Pricing or the Shopify Billing API correctly** | El código verifica identidad, catálogo y suscripción; varias activaciones dependen de configuración/evidencias y permanecen protegidas. | Probar aceptación, rechazo, reintento y aprobación tras reinstalación, importes/periodos/trial y suspensión de acceso. No activar flags de entitlement ni publicar planes para simular una prueba superada. [Verificación](../backend/app/services/shopify_billing_verification.py), [workspace](../frontend/src/pages/ShopifyBillingWorkspace.tsx). |
| **1.2.3 — Allow pricing plan changes** | Existe acceso a la página de planes Shopify y revisión/aplicación de transiciones verificadas. | Probar upgrade/downgrade sin soporte ni reinstalación y comprobar historial de cargos/entitlements. Un enlace generado no demuestra que los planes estén habilitados y el cambio sea utilizable. [Transiciones](../backend/app/services/shopify_plan_transition_review.py). |
| **2.3.3 — Redirect to the app UI after installation** | El callback público conduce a `https://diaglob.tech/shopify/install?authorized=1`, mientras la configuración es embedded. El flujo gestionado también sale a DIAGLOB para asociar una cuenta. | Verificar el retorno final a Shopify Admin/App Home y que el reviewer no quede en el portal externo. No cambiar el callback a ciegas: el handoff actual custodia la autorización temporal y requiere una vinculación explícita de tenant. [Callback](../backend/app/api/shopify.py), [destino](../backend/app/services/shopify_public_install.py). |
| **2.3.4 — Require OAuth authentication immediately after reinstall** | Hay token exchange, credenciales offline renovables, recuperación de instalaciones y tratamiento de registros previos. | Probar desinstalación/reinstalación real con el mismo merchant y otro staff, renovación de credenciales y ausencia de asociaciones duplicadas/no autorizadas. Las pruebas simuladas no acreditan el estado de Shopify. |

### ✅ Índice de evidencia favorable

Estos IDs suman los **23** criterios favorables; no son certificaciones funcionales en tienda:

| IDs | Evidencia local revisada |
| --- | --- |
| 1.1.2, 1.1.7 | Checkout Shopify y bloqueo de procesadores externos; helpers COD/PoC retirados; enlace de factura conversacional validado como HTTPS del shop autenticado. [Draft orders](../backend/app/shopify_orders.py), [checkout](../backend/app/services/conversational_checkout_service.py), pruebas de pagos y Shopify. |
| 1.1.3, 1.1.8, 1.1.10, 1.1.14, 1.1.16 | No se detectaron descarga/instalación de temas, POS externo, reordenación de envíos, marketplace de agencias ni préstamos en la superficie/configuración inspeccionada. Son conclusiones de ausencia en la fuente, no sobre un listing externo. |
| 1.1.6 | Tienda única por operación, filtros de organización/tienda y pruebas de aislamiento; no se detectó un marketplace multivendedor dentro de una tienda. |
| 1.1.9 | El draft activo se construye con variantes y cantidades, sin recargos opcionales automáticos; el mensaje de confirmación remite pago, envío y total final a Shopify. La implementación COD antigua ya no añade nada. [Input](../backend/app/shopify_orders.py), [confirmación](../backend/app/services/conversational_checkout_service.py). |
| 1.1.15 | La devolución usa el proveedor y `provider_transaction_id` de la transacción original; nueva regresión incluso después de conectar Shopify. Los reembolsos no deben ofrecer otro medio: store credit Shopify requeriría `refundCreate`/`returnProcess`, no saldo arbitrario. |
| 2.2.1, 2.2.3, 2.2.4 | Cliente Admin GraphQL, App Bridge servido desde el CDN oficial como primer script y ausencia de llamadas Admin REST generales en los módulos Shopify inspeccionados. [Cliente](../backend/app/shopify_client.py), [App Home](../backend/app/api/shopify_embedded.py). |
| 2.2.6, 2.2.7 | Sin extensiones Admin declaradas ni lanzamiento automático de Max modal en la fuente revisada. |
| 2.3.1, 2.3.2 | Conexión manual retirada; no se solicita dominio en configuración general. Instalación gestionada verifica Shopify antes del grant; OAuth valida state/HMAC e intercambia credenciales. [Rutas](../backend/app/api/shopify.py), [instalación](../backend/app/services/shopify_managed_installation.py), pruebas backend/frontend. |
| 3.1.1 | URLs HTTPS y comprobaciones públicas de ambos hosts sin omitir validación TLS; HTTP redirige a HTTPS. No acredita todos los endpoints futuros ni renovación del certificado. |
| 3.2.1, 3.2.2, 3.2.3, 3.2.4, 3.2.5 | Ninguno de los cinco scopes especiales de estos criterios está solicitado. El TOML y `SHOPIFY_SCOPES` coinciden en **siete** scopes. Esto no aprueba PCD ni justifica automáticamente cada permiso restante. |

### ⏭️ Grupos omitidos

| Grupo | Motivo | Requisitos |
| --- | --- | ---: |
| 5.1 Online store | Sin `shopify.extension.toml` de tipo `theme`. | 3 |
| 5.2 Payment | Sin extensión `payment` ni `write_payment_gateway`. | 8 |
| 5.3 Payment facilitator | Opt-in no solicitado. | 1 |
| 5.4 Purchase option | Sin scopes de métodos de pago/contratos de suscripción ni payment mandate. | 16 |
| 5.5 Product sourcing | Opt-in en el pase base; **evaluado en la autoevaluación vigente** por capacidad seleccionada en Partner. Ver 5.5.1/5.5.2 en el addendum. | 3 |
| 5.6 Checkout customization | Sin extensión UI con targets checkout. | 6 |
| 5.7 Sales channel | Sin extensión `channel_config`. No seleccionar Sales Channel solo para rellenar un campo del listing. | 14 |
| 5.8 Post purchase | Sin extensión `checkout_post_purchase`. | 10 |
| 5.9 Mobile app builders | Opt-in no solicitado. | 2 |
| 5.10 Donation | Opt-in no solicitado. | 6 |

La plantilla de web pixel en staging no convierte la app en una de estas categorías y no fue instalada ni publicada.

## Bloqueos reales fuera del subconjunto de 31 criterios

| Prioridad / estado | Hallazgo actual | Trabajo y evidencia para cerrarlo |
| --- | --- | --- |
| **P0 — Privacidad: cobertura local integral implementada; verificación externa pendiente** | La fase 3 añadió inventario efectivo por tienda de las seis áreas, manifiesto de **16 subprocesadores** en bijección con los controles (confirmación de encargados por digest), cobertura de superficies de backup y drill de restauración con ledger externo. La ejecución real sigue **deshabilitada por defecto** y todo resultado mantiene `fulfillment_complete=False`. | Verificación independiente de cada control; aprobación legal de retención/holds; backups reales con caducidad y ancla offsite operadas fuera de la app; borrado verificado en procesadores externos; activación solo con política adoptada por hash y permisos por caso. **No quitar estos bloqueos ni marcar solicitudes completas para hacer pasar la revisión.** |
| **P0 — PCD solicitado pero no aprobado** | Los cinco campos ya figuran `REQUESTED` con motivos correctos y el cuestionario está 16/16 «Sí», pero Shopify marca la app como **no aprobada** para datos protegidos; la aprobación llega con la revisión de la publicación. | Enviar la publicación cuando el resto de bloqueos esté cerrado; Shopify revisará el uso frente al listing. No dar por aprobado el acceso hasta recibir la notificación. [Webhooks](../backend/app/services/shopify_webhook_service.py), [draft input](../backend/app/shopify_orders.py). |
| **P0 — Onboarding/retorno embedded sin E2E** | Existe retorno canónico a App Home y pantalla de vinculación con código de un solo uso, verificado por pruebas sintéticas; no se ejecutó el recorrido real completo. | Ejecutar instalación nueva, selección de tienda, vinculación de staff, recarga y retorno en `diaglob-poc` con acción autorizada; probar también sesión incógnita y segundo staff. No crear membresías automáticamente por conocer el dominio o recibir un JWT. |
| **P0 — Billing/planes sin evidencia** | Tres planes públicos y dos privados existen en el listing; la tienda es de desarrollo (plan mostrado Basic). No se aceptó ningún plan. | Autorizar la prueba en la dev store (Shopify App Pricing en dev store de la misma org aplica $0), probar alta, rechazo, upgrade/downgrade, trial y reinstalación, y comparar entitlements. |
| **P1 — Configuración activa verificada; token offline obsoleto** | Versión activa, scopes, callback, App Home y webhooks de privacidad **coinciden** con el TOML local. Dev Dashboard muestra «Token offline obsoleto — Corrección vencida» (20-10-2026). | El código local ya usa `expiring=1` y refresh rotatorio; resolver el aviso requiere despliegue y renovación/reinstalación de credenciales en la tienda, con autorización. Verificar entregas webhooks firmadas/deduplicación/reintentos en el entorno real. |
| **P1 — Listing y reviewer** | Listing completo con planes, categoría, capturas, dos cuentas de prueba y screencast público. | Verificar contenido real del screencast, claims frente a lo funcionando, soporte/inbox monitorizado y credenciales de revisor entregadas solo mediante el formulario privado de Shopify. |

El número de campos pendientes del listing **no se conoce hoy**: las doce incidencias de 2026-10-11 y el screenshot 8/9 de 2026-10-20 son evidencia histórica, no el estado actual de Partner. Tras retirar el PoC interno, revisar también la justificación de `write_orders`; esta revisión no cambió scopes solicitados ni instalados.

## Validación realizada

| Comprobación | Resultado |
| --- | --- |
| Shopify CLI `app config validate --json` | Válida, cero incidencias (fase 1 y fase 2: `{"valid":true,"issues":[]}`). |
| Preflight local | `source_consistent=true`, sin blockers de fuente, **`release_authorized=false`**, `shopify_approval_verified=false`. |
| Primera selección enfocada; repetición con procedencia organizacional y gate de producción | **128 passed**. |
| Revisión ampliada Shopify + checkout conversacional + límites de autorización | **1234 passed** en 396,96 s; anterior a la última ampliación del bloqueo de pagos/helper PoC. |
| Pasada intermedia con nuevas regresiones | 1319 correctas y cuatro fallos por datos incompletos en pruebas nuevas: faltaban `tags`/`note` en llamadas legacy y `provider` en el body HTTP. Se corrigieron los fixtures sin cambiar validaciones ni aserciones. |
| Repetición enfocada tras corregir los fixtures | **234 passed** en 69,59 s. |
| Repetición final ampliada, incluyendo pagos y últimas regresiones | **1323 passed**, cero fallos/omisiones, en **406,71 s**. |
| Selección ampliada de fase 2 (todos los `test*shopify*.py` + pagos, checkout conversacional y regresiones de autorización de tienda, con las nuevas pruebas de navegación, CSP, embedded entry, ejecución de privacidad local y token lifecycle) | **194 passed** en 138,77 s, cero fallos. |
| Fase 3: selección completa Shopify (`test*shopify*.py`, incluidas las pruebas nuevas de inventario por tienda, subprocesadores y backups/drills) | **1159 passed**, cero fallos, en 151,98 s. |
| Fase 3: pagos, checkout conversacional y regresiones de autorización de tienda | **220 passed**, cero fallos, en 213,03 s. |
| Ruff `app/ tests/ tools/` y script de secretos | Correcto (fase 1 y fase 2). |
| Importación `app.main` y parseo YAML de ambos workflows | Correctos. |
| Frontend `npm test` | Fase 1: **141 passed**; fase 2: **143 passed**, cero omitidas. |
| Frontend `npm run build` | Correcto en ambas fases; conserva advertencias previas de bundle grande e importación dinámica inefectiva. |
| Frontend `npm run lint` (fase 2) | Cero errores; 172 advertencias de deuda preexistente, no introducidas por esta revisión. |
| `git diff --check` | Correcto; avisos Git de normalización LF/CRLF. |

Las selecciones se solapan: **no sumar sus conteos** como pruebas únicas. Se usan SQLite de prueba, credenciales AWS ficticias y proveedores simulados; reconciliación de inicio y analytics desactivados. Entorno local Windows/Python 3.12, no ejecución de GitHub Actions Ubuntu/Python 3.11. La selección final conserva 12257 advertencias; no se desactivaron reglas ni se corrigió deuda ajena a esta revisión para ocultarlas. El artefacto final JUnit está fuera del repositorio en `C:\Users\adria\AppData\Local\Temp\opencode\diaglob-shopify-review-final-2026-10-26.xml`.

Para reproducir la selección final en PowerShell, desde `backend`, con dependencias instaladas y un entorno **de prueba**, no de producción:

```powershell
$env:DATABASE_URL = "sqlite:///:memory:"
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_ACCESS_KEY_ID = "testing"
$env:AWS_SECRET_ACCESS_KEY = "testing"
$env:KNOWLEDGE_RECONCILE_ON_STARTUP = "false"
$env:PRODUCT_ANALYTICS_ENABLED = "false"
$tests = Get-ChildItem tests -Filter "test*shopify*.py" | Sort-Object Name | ForEach-Object { "tests/$($_.Name)" }
$tests += "tests/test_payments.py"
$tests += "tests/test_conversational_cod_checkout.py"
$tests += "tests/test_conversational_cod_checkout_hardening.py"
$tests += "tests/test_store_authorization_regressions.py"
python -m pytest -q --tb=short --disable-warnings @tests
```

La suite completa anterior terminó con **2892 passed, 2 failed** (2144,14 s): ambos fallos Windows pertenecían al bootstrap de secretos y se corrigieron con las regresiones enfocadas. **No se declara la suite completa actual en verde**, pues no se repitieron todos los dominios después de estos cambios. Véase [reporte de hardening actualizado](engineering-hardening-progress-2026-10-26.md).

### Comprobaciones públicas limitadas

- Privacidad, términos y soporte: HTTPS responde 200. Son comprobaciones de disponibilidad, no revisión legal ni prueba de recepción de los buzones.
- App Home (fase 1): **GET HTTPS 200**, `Cache-Control: no-store` y CSP `frame-ancestors https://admin.shopify.com https://*.myshopify.com`; no `X-Frame-Options: DENY` en esa respuesta. HEAD devuelve 405 porque la ruta solo admite GET; no es un fallo de disponibilidad del recorrido GET. Esa CSP con comodín fue **reemplazada en fase 2** por una CSP dinámica sin comodín; el estado observado en fase 1 correspondía al servicio desplegado, no al árbol local.
- `curl.exe` confirmó **301 de HTTP a HTTPS** tanto para privacidad como para App Home/API. No se desactivó la validación de certificados. Un fetch intermediado que devuelve el contenido final no demuestra ausencia de redirección.
- Shopify Partners (solo lectura salvo la autorizada respuesta PCD): versión activa, scopes, webhooks, listing y detalle de la app verificados en el panel real el 26-10-2026; véase la tabla de evidencias de fase 2.
- Shopify Admin en `diaglob-poc.myshopify.com`: la app aparece instalada y su App Home abre dentro del Admin (iframe real observado). No se ejecutó reinstalación, vinculación de segundo staff ni prueba de planes.
- Estos resultados corresponden al estado observado; **no** prueban que los cambios locales estén desplegados ni que Shopify haya autorizado un iframe/sesión de comerciante real para usuarios finales.

## Puerta de salida y operación

1. Cerrar la implementación de privacidad con revisión legal/operativa y pruebas autorizadas; no ejecutar borrado o entrega real sin aprobación específica.
2. Obtener evidencias PCD, versión/scopes activos y planes de la app correcta.
3. Ejecutar instalación nueva, selección de tienda, vinculación de staff, recarga, rechazo de cobro, cambio de plan y reinstalación en Shopify Admin, incluida sesión incógnita.
4. Completar listing/cuenta reviewer/screencast con lo que realmente funciona; repetir CI sobre el SHA final y comprobar el servicio después de un despliegue autorizado.
5. Solo entonces considerar el envío. **Shopify decide la aprobación oficial.**

No se requiere migración para estas correcciones. Un rollback de código debe volver a un artefacto previamente validado, con revisión específica: no restaurar una vía de cobro externo prohibida. La modificación del workflow solo agrega validación previa; no altera SSH, secretos, migraciones ni el script remoto de despliegue, y no lo ejecuta.

## Referencias

- [Requisitos de App Store](https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements)
- [Buenas prácticas](https://shopify.dev/docs/apps/launch/shopify-app-store/best-practices)
- [Facturación de apps](https://shopify.dev/docs/apps/launch/billing)
- [Protected customer data](https://shopify.dev/docs/apps/launch/protected-customer-data)
- [Privacidad](https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance)
- [Enviar una app a revisión](https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review)
