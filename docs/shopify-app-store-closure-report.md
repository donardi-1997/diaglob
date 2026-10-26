# DIAGLOB — informe de cierre técnico de Shopify App Store

**Fecha:** 2026-10-26
**Estado:** **NO-GO para enviar**. No se envió la publicación, no se marcaron declaraciones como completadas y no se modificó el Partner Dashboard.
**Alcance:** código, configuración local, pruebas sintéticas, lecturas autorizadas de Shopify Partner y una auditoría AWS de solo lectura. Este informe no certifica cumplimiento legal, aprobación PCD ni funcionamiento de servicios externos.

## 1. Estado inicial y repositorio

| Elemento | Estado comprobado al inicio |
| --- | --- |
| Rama | `main` |
| HEAD local | `fe31eda` — `feat(docs): add Shopify privacy evidence pack and independent review checklist` |
| `origin/main` | `63a110e` — snapshot de rutas para el CI |
| Relación local/remoto | Local `main` estaba 1 commit adelante; código de aplicación idéntico al remoto en ese momento. |
| Cambios locales preexistentes | Había dos documentos modificados y dos documentos nuevos de las tareas de evidencia anteriores. Se preservaron y no se descartaron. |
| Pull requests | `gh pr list --state open` no devolvió PR abiertos al inicio. No hay plantilla de PR bajo `.github/`. |
| Protección de `main` | GitHub reportó que `main` no tiene branch protection. El workflow de PR valida `pull_request`; el workflow de producción se activa por `push` a `main`. |
| Último deploy conocido | Run `40407310191`, commit `63a110e`, **Validate + Deploy Production + Telegram en verde**. Ningún cambio de esta sesión se ha desplegado. |
| Shopify Dev Dashboard | `diaglob-scopes-1` aparece activa; la vista de versiones describe el candidato `a52238d` como “Scope candidate only; not approved for release”. No se creó ni liberó otra versión. |

El commit local `fe31eda` y los documentos existentes **no se asumen publicados en GitHub**. El estado del árbol se vuelve a registrar al final de este trabajo. No se hizo merge ni deploy.

## 2. Resumen ejecutivo

- La revisión PCD sigue siendo **Level 2**: la app recibe y persiste nombre, dirección, email y teléfono desde datos de pedidos/webhooks aunque no solicite `read_customers`.
- Partner muestra la publicación como `Attention / Borrador / Listo para enviar`; la publicación no se envió ni tiene observaciones humanas de reviewer. La lectura más reciente muestra la comprobación automática superada y el paso de solicitud PCD completado. La página PCD sigue en `Borrador`, con **16/16 “Sí”** visibles y la app expresamente **no aprobada** para datos protegidos. Una lectura anterior mostró “No necesita PCD”; después apareció “Solicitud PCD completada”. No se conoce el origen de esa transición y el agente no guardó cambios.
- Entre dos lecturas de la página de distribución, la UI cambió de “No necesita acceso PCD” a “Solicitud de acceso PCD completada”. El agente no guardó ni cambió nada. Se debe confirmar con el propietario qué estado se guardó realmente; “solicitud completada” no equivale a aprobación.
- Se corrigió código local en la última frontera de publicación de fulfillment: ahora se vuelven a validar pago/estado, privacidad y vínculo organization/store justo antes de llamar a Shopify. No se añadieron scopes ni llamadas reales.
- El product sourcing declarado sigue bloqueado por dos requisitos: Shopify documenta `fulfillmentOrderSubmitFulfillmentRequest` con `write_third_party_fulfillment_orders` y un fulfillment service asignado; el código actual usa fulfillment merchant-managed. Tampoco hay flujo que publique COGS a Shopify; `inventoryItemUpdate` requiere `write_inventory`, no solicitado. No es seguro añadir estos scopes/funciones sin decidir una arquitectura y su necesidad.
- El auditor AWS de solo lectura no pudo autenticar las credenciales configuradas (`InvalidAccessKeyId`/`UnrecognizedClientException`); backups, cifrado y restore permanecen sin verificar.
- No se puede confirmar que todas las respuestas afirmativas de PCD sean verdaderas. Retención, cifrado integral, backups, separación de entornos, DLP, accesos, contraseñas, logs e incidentes requieren evidencia adicional o intervención externa/humana.

## 3. Matriz de requisitos y brechas

Estados según el encargo:

- **VERIFICADO:** control y evidencia concluyente comprobados.
- **CORREGIDO, PENDIENTE DE VALIDACIÓN:** código local corregido, requiere pruebas o evidencia adicional para cerrar.
- **BLOQUEADO EXTERNAMENTE:** depende de Shopify, proveedor, AWS/Cognito, despliegue o configuración fuera del repo.
- **REQUIERE DECISIÓN HUMANA:** requiere aprobación del titular, seguridad, legal o decisión de producto.
- **PENDIENTE:** trabajo/evidencia aún no realizado.

### 3.1 Partner Dashboard, PCD y publicación

| Requisito | Estado comprobado | Evidencia | Riesgo | Corrección / prueba necesaria | Resultado |
| --- | --- | --- | --- | --- | --- |
| Publicación y observaciones de reviewer | Borrador; no enviada; sin comentarios humanos | Lectura de `Distribution → App Store`; estado `Attention / Borrador / Listo para enviar` | No existe dictamen de Shopify | No enviar hasta cerrar bloqueos; conservar el estado draft | **PENDIENTE** |
| Comprobación automática de errores frecuentes | La lectura más reciente muestra `superada`; lectura anterior del mismo turno mostraba error de servidor | DOM actual del Partner Dashboard, sin interacción de ejecución | Cambio de estado no atribuible; no prueba review humano | Propietario confirma el estado guardado; conservar evidencia saneada | **PENDIENTE** |
| Selección/declaración PCD | Paso PCD aparece “completado”; la página PCD sigue `Borrador`, última actualización visible 20-10-2026, no aprobada, con 16/16 respuestas “Sí” | Lectura de `customer_data` y `customer_data/details` | Un “Sí” es una atestación, no una prueba; algunos no están sustentados | Contrastar y corregir manualmente cuando el dueño autorice; no marcar autoevaluación como completada | **REQUIERE DECISIÓN HUMANA** |
| Contradicción del resumen PCD | Una lectura mostró “No necesita PCD”; otra, “Solicitud de acceso PCD completada” | Dos lecturas de solo lectura; el agente no guardó cambios | Riesgo de publicar una declaración incoherente con los cuatro campos que la app procesa | Confirmar qué respuesta quedó guardada y reconciliar listing, scopes y uso real | **REQUIERE DECISIÓN HUMANA** |
| Aprobación PCD Level 2 | No aprobada | Partner Dashboard indica que no está aprobada | Shopify puede redacted/null los campos hasta aprobar; review público bloqueado | Solicitud y decisión de Shopify después de evidencias Level 1+2; no se solicita desde esta sesión | **BLOQUEADO EXTERNAMENTE** |
| Scopes y webhooks declarados | 7 scopes locales y 3 temas de privacidad; preflight sin deriva | `shopify.app.toml`, `SHOPIFY_SCOPES`, `shopify_review_source_preflight` | Fuente coherente no demuestra grants/versiones activas | La versión Shopify activa y grants deben confirmarse por separado antes de cualquier release | **CORREGIDO, PENDIENTE DE VALIDACIÓN** |

### 3.2 Preguntas de protección de datos PCD (1–16)

Shopify exige Level 1 y Level 2 para usar esos campos en una app pública. El estado “VERIFICADO” no se asigna por disponer de una política o un hash.

| Pregunta | Estado/evidencia real | Evidencia faltante / riesgo | Resultado |
| ---: | --- | --- | --- |
| 1 — Minimización | Scopes acotados y campos order-linked identificados | Mapa completo campo→finalidad, derivados, automatizaciones, AI, y necesidad de cada campo | **PENDIENTE** |
| 2 — Transparencia al merchant | Existen páginas/documentos de privacidad | Acreditar que el contenido publicado, DPA, lista de procesadores y onboarding están vigentes y alineados | **PENDIENTE** |
| 3 — Limitación de propósito | Hay funcionalidades de órdenes, automatizaciones, scoring e IA | Verificación de uso secundario, controles y cobertura por todos los procesadores | **PENDIENTE** |
| 4 — Acuerdo de privacidad con merchants | No se proporcionó DPA/aceptación versionada | Evidencia de contrato vigente y aceptación por merchant | **REQUIERE DECISIÓN HUMANA** |
| 5 — Consentimiento | Controles parciales en algunos productos | Matriz de finalidad y prueba E2E para cada uso que requiera consentimiento | **PENDIENTE** |
| 6 — Opt-out de venta/compartición | No se afirma venta; hay proveedores a quienes se transmiten datos | Análisis jurídico de “sale/sharing” y mecanismo cuando aplique; no usar N/A por suposición | **REQUIERE DECISIÓN HUMANA** |
| 7 — Decisiones automatizadas significativas | Existen scoring/riesgo y AI | Análisis del efecto legal/significativo y opt-out/manual si aplica | **REQUIERE DECISIÓN HUMANA** |
| 8 — Retención efectiva | Política local es propuesta; ejecución de privacidad fail-closed/deshabilitada por defecto | Calendario legal aprobado, jobs efectivos, borrado/expiración y reconciliación | **BLOQUEADO EXTERNAMENTE** |
| 9 — Cifrado en reposo y tránsito | HTTPS público y Fernet para secretos Shopify | Cifrado de datos PCD en DB/disco/servicios, claves, enlaces internos/externos | **BLOQUEADO EXTERNAMENTE** |
| 10 — Backups cifrados | Auditor read-only ejecutado; todas las APIs AWS rechazaron las credenciales actuales | Configuración real de cifrado, claves, retención y restore | **BLOQUEADO EXTERNAMENTE** |
| 11 — Separación prueba/producción | La tienda POC de desarrollo usa el App Home del backend `api.diaglob.tech` | Backend/BD/credenciales aislados y prueba de ausencia de PII prod en staging/test | **BLOQUEADO EXTERNAMENTE** |
| 12 — DLP | No hay evidencia de DLP integral de endpoint/egress/monitoring en el repo | Controles organizacionales e infraestructura, owner y pruebas | **BLOQUEADO EXTERNAMENTE** |
| 13 — Acceso de staff limitado | Rutas de clientes tienen permission + filtros org/store; pruebas sintéticas | Auditoría de todas las rutas PCD, IAM/operaciones y E2E | **CORREGIDO, PENDIENTE DE VALIDACIÓN** |
| 14 — Contraseñas fuertes | Cognito usa el producto; configuración activa del User Pool no está en el repo | Lectura autenticada de política actual (longitud/complejidad/MFA si aplica) y evidencia saneada | **BLOQUEADO EXTERNAMENTE** |
| 15 — Registro de accesos | `CUSTOMER_PCD_READ` registra algunas lecturas sin PII | Cobertura integral, almacenamiento central, retención, acceso y revisión frecuente | **PENDIENTE** |
| 16 — Respuesta a incidentes | Documento local todavía se declara “propuesta para adopción” | Aprobación, responsables/contactos, guardia/escala y ejercicio comprobable | **REQUIERE DECISIÓN HUMANA** |

El acceso PCD seleccionado incluye nombre, email, teléfono y dirección; el código recibe estos campos desde webhooks/pedidos. Q8–Q16 no pueden considerarse cumplidos hasta verificar el control operativo, aunque las preguntas estén contestadas “Sí”.

### 3.3 Privacidad, webhooks, eliminación y backups

| Requisito | Estado comprobado | Evidencia/pruebas | Riesgo/pendiente | Resultado |
| --- | --- | --- | --- | --- |
| Recepción segura de `customers/data_request`, `customers/redact`, `shop/redact` | Validación HMAC, persistencia/idempotencia y tareas de revisión implementadas localmente | `shopify.app.toml`, `shopify_compliance_webhooks.py`, tests de compliance/webhook | Entrega real firmada y subscription en versión activa no confirmadas en esta sesión | **CORREGIDO, PENDIENTE DE VALIDACIÓN** |
| Exportación/redacción real | Hay implementación local con permisos/ancoras, pero permanece desactivada por defecto | Suite sintética de privacidad | No correr PII real ni activar ejecución sin permiso por caso y autoridad | **PENDIENTE** |
| Alcance de eliminación | Inventario por tienda, controles y supresiones locales; bloqueos de atribución permanecen | Tests `test*shopify*.py` y flujo fail-closed | No se demuestra borrado completo en proveedores, archivos, logs y datos reales | **PENDIENTE** |
| Backups/restore | Herramienta de auditoría explicitamente read-only; resultado AWS actual `unverified` | `tools.diaglob_aws_privacy_audit` | Credenciales no válidas; restore, cifrado y caducidad no acreditados | **BLOQUEADO EXTERNAMENTE** |
| Proveedores/subprocesadores | Manifiesto local de 16 candidatos, todos no verificados | `shopify_privacy_subprocessors.py` y paquete de evidencia | Lista legal real, contratos, uso efectivo, retención y respuestas de proveedores | **BLOQUEADO EXTERNAMENTE** |

### 3.4 Product sourcing / fulfillment

| Requisito | Evidencia | Corrección/decisión | Estado |
| --- | --- | --- | --- |
| No publicar fulfillment tras reembolso/cancelación o supresión PCD | Revalidación agregada en `sync_shopify_from_shipment` antes de mutar Shopify; shipment, supplier order, job y order vinculados por org/store/provider/order | Tests sintéticos bloquean llamada a Shopify y mantienen order no fulfilled | **CORREGIDO, PENDIENTE DE VALIDACIÓN** |
| 5.5.1 Solicitud al fulfillment service | Admin GraphQL 2026-07 exige `write_third_party_fulfillment_orders` y FulfillmentOrder asignado a un fulfillment service; DIAGLOB usa scopes merchant-managed y `fulfillmentCreate` | Requiere decisión de producto/arquitectura, registro de service/location, scopes y flujo de aceptación/rechazo. No se añade scope en esta entrega | **BLOQUEADO / DECISIÓN HUMANA** |
| 5.5.2 Cost of goods sold en Shopify | `inventoryItemUpdate` requiere `write_inventory`; no hay escritura de productos/costos en la integración Shopify actual | Determinar si DIAGLOB debe publicar catálogo/costos y justificar scope adicional antes de implementar | **BLOQUEADO / DECISIÓN HUMANA** |
| 5.5.5 Pago antes del fulfillment | Guard paid/confirmed COD y nueva verificación justo antes del fulfillment desde shipment | 19 pruebas focalizadas pasan; falta E2E real | **CORREGIDO, PENDIENTE DE VALIDACIÓN** |

### 3.5 Scopes/configuración, CI, pruebas y GitHub

| Elemento | Resultado exacto | Estado |
| --- | --- | --- |
| `shopify app config validate --path . --json` | `valid=true`, `issues=[]` | **VERIFICADO (config local)** |
| `shopify_review_source_preflight` | Source consistent, no scope drift; `release_authorized=false`, PCD no verificado | **VERIFICADO (source only)** |
| `shopify_scope_release_preflight` | candidato local consistente; no versión creada/liberada, grants y PCD no verificados | **VERIFICADO (source only)** |
| `tests/test_auto_fulfillment.py`, `test_dropi_adapter_readiness.py`, `test_shopify_fulfillment.py` | **19 passed** en SQLite/proveedores sintéticos | **VERIFICADO (focalizado)** |
| Ruff, archivos modificados | Ruff limpio | **VERIFICADO** |
| Suite backend completa | En ejecución al redactar este informe; actualizar con el resultado final antes de enviar PR | **PENDIENTE** |
| AWS audit PCD | `mode=read_only`, `production_changes=false`; S3 `InvalidAccessKeyId`, Lightsail/AWS Backup/Bedrock `UnrecognizedClientException`; Q10/restore false | **BLOQUEADO EXTERNAMENTE** |
| Pull requests | No había PR abierto al inspeccionar | **VERIFICADO (GitHub read-only)** |
| Branch/commit/deploy | Rama local `main`, `fe31eda`; `origin/main=63a110e`, un commit local adelante. Último deploy conocido Run `40407310191` en `63a110e`; este parche aún no desplegado | **PENDIENTE DE PR; no desplegado** |

## 4. Cambios implementados en esta sesión

`backend/app/services/auto_fulfillment.py::sync_shopify_from_shipment` ahora:

1. acepta únicamente shipments CJ y exige que proveedor, supplier order, shipment, auto job y order coincidan en organización/tienda/order;
2. vuelve a validar elegibilidad de pago/estado (`paid` o COD confirmado, no refund/cancel/final) inmediatamente antes de llamar a Shopify;
3. vuelve a consultar el gate local de privacidad/tombstones antes de publicar tracking o notificar al comprador;
4. ante order no elegible o supresión, registra `skipped` con código estable y no ejecuta `fulfillmentCreate`.

Se añadieron regresiones sintéticas en `backend/tests/test_auto_fulfillment.py` para reembolso después de crear el supplier order, supresión PCD antes del shipment sync y supplier order de otra tienda. No se añadió scope, mutación nueva a Shopify, migración ni operación remota.

## 5. Bloqueos externos y decisiones humanas

1. Confirmar en Partner qué estado de la solicitud PCD está guardado; nunca inferir aprobación de “paso completado”.
2. Un responsable de seguridad/legal debe revisar y corregir las 16 respuestas; hay varias “Sí” no sustentadas. No guardar cambios sin autorización del propietario.
3. AWS: reemplazar/renovar credenciales a través del mecanismo seguro y volver a correr el auditor read-only. No pegar credenciales en chat o repo.
4. Cognito: confirmar la política activa de contraseña/MFA con la cuenta autorizada y guardar evidencia saneada.
5. Producción/test: decidir y aprovisionar un backend/BD/credenciales aislados para la tienda POC antes de atestar separación.
6. Producto: decidir si DIAGLOB realmente ofrece product sourcing compatible con el flujo Shopify. Si sí, diseñar la fulfillment service y coste/catálogo junto con los scopes mínimos; si no, el dueño deberá cambiar la capacidad del listing (el agente no lo hizo).
7. Procesadores: obtener DPA y confirmación de retención/eliminación de cada proveedor aplicable.
8. No marcar la autoevaluación, no enviar publicación/PCD y no hacer deploy/merge hasta completar los gates que dependan de estas decisiones.

## 6. Referencias

- [Autoevaluación IA de Shopify](shopify-app-store-ai-review-2026-10-26.md)
- [Matriz de trazabilidad de privacidad](shopify-privacy-traceability-review-2026-10-26.md)
- [Paquete operativo de evidencias PCD](shopify-privacy-evidence-pack-2026-10-26.md)
- [Revisión/remediación previa](shopify-review-remediation-2026-10-26.md)
- Shopify Admin GraphQL 2026-07: [`fulfillmentOrderSubmitFulfillmentRequest`](https://shopify.dev/docs/api/admin-graphql/2026-07/mutations/fulfillmentOrderSubmitFulfillmentRequest) y [`inventoryItemUpdate`](https://shopify.dev/docs/api/admin-graphql/2026-07/mutations/inventoryItemUpdate).

## 7. PR y release

- Se preparó la rama `feat/shopify-app-store-closure-2026-10` y un **PR draft #318** contra `main`: https://github.com/donardi-1997/diaglob/pull/318.
- HEAD del PR: commit `836494c` (`fix(shopify): recheck payment and privacy before fulfillment`). La rama parte del `fe31eda` local anterior y apunta a `origin/main` `63a110e`; el PR agrupa la evidencia local de privacidad y el cierre técnico relacionado.
- Run de validación del PR observado al redactar: `40414659417`; `Detect changed scopes` pasó, backend shards estaban pendientes y frontend/mobile se omitieron porque el cambio no los afecta.
- **No se fusionó el PR, no se empujó a `main`, no se desplegó a producción y no se presentó la app ni PCD a Shopify.** El último deploy conocido sigue siendo el run `40407310191` sobre `63a110e`.
