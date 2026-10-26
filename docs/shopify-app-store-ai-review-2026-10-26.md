# DIAGLOB — AI self-review de Shopify App Store y Protected Customer Data

**Resultado: NO-GO; no se puede confirmar que se cumplan todos los requisitos.** Esta es una evaluación previa al envío, no una revisión/aprobación de Shopify. No se enviaron formularios, no se marcó la autoevaluación como completada y no se ejecutaron operaciones sobre clientes, proveedores, instalaciones o producción.

**Alcance y fuentes:** Shopify CLI 4.9.4 obtuvo los requisitos canónicos de App Store y PCD el 2026-10-26. El Partner Dashboard se revisó en modo de solo lectura. El código local se contrastó con `shopify.app.toml`, los webhooks y las rutas/servicios relacionados. Se intentó SSH de solo lectura; no se pudo verificar la identidad Diaglob del host ni acceder a la configuración AWS/Cognito de producción o a un repositorio externo de evidencias.

## Resumen de criterios de App Store

El documento canónico descargado enumera **100 requisitos**. Se evaluaron los 31 criterios generales del expediente existente y los 3 criterios de product sourcing, porque Partner muestra la capacidad **“abastecimiento de productos”** y el usuario pidió revisar todos los criterios.

| Resultado | Número | Alcance |
| --- | ---: | --- |
| ✅ Likely passing | **24** | Evidencia local suficiente para revisión preliminar; no es aprobación Shopify ni E2E de tienda |
| ❌ Likely failing | **2** | 5.5.1 y 5.5.2, si se mantiene la capacidad product sourcing seleccionada |
| ⚠️ Needs review | **8** | Falta verificación humana, comercial, legal o E2E |
| ⏭️ Skipped | **66** | Nueve grupos condicionales no aplicables o categorías que DIAGLOB no ofrece |

Los 66 omitidos corresponden a 5.1 Theme, 5.2 Payment app, 5.3 Payment facilitator, 5.4 Purchase option, 5.6 Checkout UI extension, 5.7 Sales channel, 5.8 Post-purchase, 5.9 Mobile app builder y 5.10 Donation. No se encontró su señal de aplicabilidad en la configuración revisada; no son una afirmación de cumplimiento para una capacidad que se agregue en el futuro.

El detalle de los 31 criterios generales (23 favorables, 8 en revisión) está en el [expediente de revisión Shopify](shopify-review-remediation-2026-10-26.md). Esta autoevaluación agrega los tres criterios de sourcing que no se evaluaron en ese expediente anterior.

### Product sourcing (aplicable a la capacidad seleccionada)

| Requisito | Evaluación | Evidencia local / brecha |
| --- | --- | --- |
| **5.5.1 — Enable merchants to request fulfillment** | ❌ **Likely failing / bloqueado por arquitectura y scopes** | No se encontró `fulfillmentOrderSubmitFulfillmentRequest`. Shopify documenta que requiere `write_third_party_fulfillment_orders` y un fulfillment service asignado. La app solo tiene scopes merchant-managed y usa `fulfillmentCreate` para publicar tracking tras la orden CJ; no se debe añadir el scope ni fingir que existe una fulfillment service. |
| **5.5.2 — Include details of cost of goods sold** | ❌ **Likely failing / requiere decisión de scope** | No se encontró una mutación/configuración que escriba el costo unitario al campo Cost de Shopify. `inventoryItemUpdate` requiere `write_inventory`, hoy no solicitado; `shopify_sync.py` lee productos/variantes, no publica costos. No ampliar scopes sin justificarlo y aprobar el flujo de producto. |
| **5.5.5 — Verify payment before marking orders as fulfilled** | ✅ **Likely passing en la ruta probada** | `auto_fulfillment.py::_eligible_order` exige `paid` o COD confirmado. En esta ejecución se añadió una revalidación de pago/estado y supresión PCD justo antes de publicar tracking, con filtros org/tienda para shipment/proveedor/job. **19 pruebas** focalizadas pasan; E2E real del proveedor/tienda sigue pendiente. |

Los dos probables incumplimientos deben corregirse o demostrarse no aplicables antes de decir que todos los requisitos están satisfechos. No se cambió la categoría o el listing.

## Estado observado en Shopify Partner

Se inspeccionaron en modo de solo lectura las páginas actuales de distribución y datos protegidos de DIAGLOB (app `416524435457`, Partner org `5148778`):

- **App Store: `Attention / Borrador / Listo para enviar`.** La publicación no se ha enviado y no hay observaciones de revisión humana de Shopify. La configuración, el contacto de emergencia, la publicación y el acceso PCD aparecen como pasos preliminares completados.
- **Comprobación automática de errores frecuentes:** una lectura inicial mostró el error del lado Shopify; en una lectura posterior el Dashboard ya muestra **“Comprobación automática superada”**. No pulsamos `Ejecutar`; el cambio apareció entre lecturas. Resultado actual visible: superada, pero no es aprobación de publicación.
- En una lectura inicial, el resumen mostraba **“No necesita acceso a datos de clientes protegidos”**; una lectura posterior muestra **“Solicitud de acceso a datos de clientes protegidos completada”**. No guardamos ni cambiamos el formulario. El origen de la transición de UI es desconocido y debe confirmarse con el propietario. La sección PCD sigue indicando que la app **no está aprobada**.
- **PCD:** estado `Borrador`, última actualización visible 20-10-2026, **16/16 preguntas contestadas**. La UI mantiene “Sí” en las 16 respuestas. Protected Customer Data y los cuatro campos **Name, Email, Phone y Address** aparecen seleccionados con los motivos “Gestión de la tienda” y “Funcionalidad de la app”. Esto es selección/declaración de borrador, no aprobación.
- La publicación ofrece las acciones **“Ejecutar”** (comprobación automática), **“Marcar como completado”** (auto-revisión) y **“Enviar a revisión”**. No se pulsó ninguna.

No hay comentarios de reviewer aún: el estado sigue siendo borrador. No enviar ni pulsar `Marcar como completado` mientras existan brechas obligatorias o declaraciones sin evidencia.

## PCD: clasificación y requisitos obligatorios

La documentación oficial de Shopify dice que una app pública que procesa datos de cliente con **nombre, dirección, teléfono o email** requiere acceso a datos protegidos y a los campos correspondientes (**Level 2**), debe cumplir **todos los requisitos Level 1 y Level 2**, y participa en una revisión de protección de datos. Los datos de cliente en pedidos y webhooks cuentan aunque no se solicite `read_customers`. DIAGLOB procesa estos campos desde webhooks de órdenes en `backend/app/services/shopify_webhook_service.py` y `shopify.app.toml` declara `read_orders` y los tres temas de privacidad.

Los requisitos PCD que Shopify formula con **“must”** son obligatorios para el nivel aplicable. Los requisitos expresamente condicionales (consentimiento, opt-out de venta/compartición y decisiones automatizadas de efectos significativos) solo pueden declararse no aplicables tras documentar el análisis. La comprobación de App Store con IA es preparación; no sustituye esta revisión ni autoriza a marcar “Sí” sin evidencia.

### Preguntas de Partner 1–16

Las respuestas actuales visibles son “Sí”; esta tabla evalúa si la evidencia examinada permite sostenerlas. “No demostrada” no afirma que no exista un control externo: significa que no hay evidencia suficiente en el código/documentos revisados para atestarlo.

| # | Tema | Estado de evidencia | Evaluación de la respuesta actual “Sí” |
| ---: | --- | --- | --- |
| 1 | Minimizar datos personales | Parcial: scopes limitados y campos de pedido documentados; faltan mapa completo campo→finalidad, datos derivados y prueba de necesidad | ⚠️ No confirmable aún |
| 2 | Informar al merchant de datos/finalidades | Hay política/documentación, pero no se verificó que el texto publicado, DPA y lista de proveedores vigentes coincidan | ⚠️ Revisión de publicación/contrato |
| 3 | Limitar el uso a finalidades declaradas | Automatizaciones, riesgo, AI y proveedores amplían los flujos; no hay verificación integral de purpose limitation | ⚠️ No confirmable aún |
| 4 | Acuerdos de privacidad con merchants | No se presentó evidencia de DPA/contrato efectivamente aceptado y versión aplicable | ⚠️ “Sí” no sustentado |
| 5 | Aplicar decisiones de consentimiento | Hay controles de consentimiento en algunas funciones, pero no prueba de cobertura en todos los flujos PCD | ⚠️ Condicional; requiere análisis por finalidad |
| 6 | Respetar opt-out de venta/compartición | No se afirma venta; existen transferencias a proveedores. No hay análisis legal/documentado de aplicabilidad y opt-out | ⚠️ No usar N/A sin revisión legal |
| 7 | Opt-out de decisiones automatizadas significativas | Hay scoring/riesgo y funciones AI; no está demostrado si tienen efecto significativo ni existe evidencia de opt-out/manual en tal caso | ⚠️ Aplicabilidad pendiente |
| 8 | Retención efectiva | La política local es una propuesta; el borrado real está bloqueado por defecto y los plazos de política no acreditan jobs/caducidad reales | ❌ “Sí” no sustentado; Level 1 obligatorio |
| 9 | Cifrado en reposo y tránsito | HTTPS y Fernet para credenciales Shopify son evidencia parcial; datos PCD de customer/order no se cifran campo a campo en la app y no se verificó cifrado de DB/disco/servicios/tránsito integral | ❌ “Sí” no sustentado; Level 1 obligatorio |
| 10 | Backups cifrados | No hay evidencia actual de cifrado de copias de PostgreSQL/servidor, custodia de claves y restauración; `diaglob_aws_privacy_audit.py` mantiene el attestation Q10 en `false` | ❌ “Sí” no sustentado; Level 2 obligatorio |
| 11 | Separación prueba/producción | La tienda POC de desarrollo abre la App Home en `https://api.diaglob.tech/api/shopify/embedded`, el backend público de producción; no se demostró un backend/datos aislados | ❌ Incumplimiento probable; Level 2 obligatorio |
| 12 | Estrategia DLP | No se encontró control/plan integral de clasificación, egress, monitoreo y respuesta contra exfiltración; el inventario de seguridad existente la marca pendiente | ❌ “Sí” no sustentado; Level 2 obligatorio |
| 13 | Limitar acceso de staff a PCD | Hay permisos y filtros organization/store en `api/customers.py` y pruebas sintéticas; el alcance de todos los endpoints/roles y acceso operativo no está auditado E2E | ⚠️ Parcial; Level 2 obligatorio |
| 14 | Contraseñas fuertes de staff | La autenticación usa Cognito, pero la política activa del User Pool/MFA no está configurada en este repo ni se consultó en AWS | ⚠️ Evidencia externa requerida; no sostener “Sí” aún |
| 15 | Registro de accesos PCD | `CUSTOMER_PCD_READ` registra algunas rutas de clientes sin PII; no se acredita cobertura de todas las lecturas PCD, centralización, retención ni revisión frecuente | ❌ Parcial; “Sí” global no sustentado; Level 2 obligatorio |
| 16 | Política de respuesta a incidentes | Existe un documento, pero declara “propuesta para adopción”; contactos, suplencias y ejercicio operativo no están acreditados | ❌ “Sí” no sustentado; Level 2 obligatorio |

**Q8–Q15 solicitadas en el plan:** Q8–Q9 son Level 1; Q10–Q15 son Level 2. Para esta app Level 2 aplica. No se recomienda cambiar ni guardar las respuestas desde esta sesión: el dueño debe corregir el borrador después de verificar controles externos y, donde no haya control, no afirmar “Sí”. La evidencia local no autoriza afirmar cumplimiento ni completar el formulario.

Fuentes de código/evidencia relevantes: [retención y ejecución fail-closed](../backend/app/services/shopify_privacy_processing.py), [cifrado limitado a secretos Shopify](../backend/app/shopify_security.py), [auditoría AWS que no attesta backups PCD](../backend/tools/diaglob_aws_privacy_audit.py), [acceso a clientes y eventos `CUSTOMER_PCD_READ`](../backend/app/api/customers.py), [regresiones de aislamiento/log](../backend/tests/test_shopify_customer_access_scope.py), [evidencia de seguridad externa anterior](shopify-pcd-security-controls-2026-10-20.md), [auditoría del POC](shopify-diaglob-poc-live-scope-audit-2026-10-20.md), [política de incidentes, aún propuesta](legal/security-incident-response-policy.md).

## Contraste de webhooks, campos y validaciones locales

- `shopify.app.toml` solicita siete scopes; no pide `read_customers`, pero declara `read_orders`, `write_draft_orders` y scopes de fulfillment. La ausencia de `read_customers` **no** elimina PCD de pedidos.
- El TOML declara `customers/data_request`, `customers/redact` y `shop/redact`. El endpoint de compliance verifica HMAC y tiene regresiones sintéticas de idempotencia y sanitización de logs. Eso prueba comportamiento local ante fixtures, no entregas reales, borrado/export E2E ni aprobación PCD.
- Los datos order-linked se persisten en customer/order fields. `shopify_privacy_processing.py` mantiene áreas sin resolver como bloqueadas; la ejecución real de privacidad sigue desactivada por defecto y no puede marcar fulfillment global completo.
- `shopify app config validate --path . --json`: `valid=true`, `issues=[]` (esquema local solamente).
- `tools.shopify_review_source_preflight`: `source_consistent=true`, sin deriva de scopes; también declara `release_authorized=false`, `shopify_approval_verified=false` y ocho clases de evidencia independiente requerida.
- `tools.shopify_scope_release_preflight`: candidato local seguro para preparar sin liberar; `new_version_created=false`, `existing_app_version_released=false`, `protected_customer_data_approval_verified=false`, `merchant_installation_e2e_verified=false`.
- Validación focalizada posterior al cambio: `tests/test_auto_fulfillment.py` + `tests/test_dropi_adapter_readiness.py` + `tests/test_shopify_fulfillment.py` — **19 passed**; Ruff limpio.
- CI del PR, run **40415324954** sobre el head `57b543a`: backend shard 0 **1391 passed** + shard 1 **1603 passed** = **2994 passed, 20 warnings, cero fallos**. También pasaron Ruff, preflight y agregador. Frontend/mobile se omitieron por alcance. La suite backend local lanzada en paralelo sigue pendiente al redactar.
- La salida anterior `InvalidAccessKeyId`/`UnrecognizedClientException` procedía de un audit local ejecutado con las credenciales dummy `testing`; no es evidencia del estado AWS de producción. La PEM indicada existe. SSH al host inicial `3.23.27.223` llegó a un servidor sin `/opt/diaglob/app` ni servicio `diaglob`; la IP corregida `3.19.202.232` rechazó la clave con `Permission denied (publickey)`. No se usó sudo, no se leyeron secretos y no se ejecutó AWS audit remoto. Backups/cifrado/restore siguen sin verificar.

## Bloqueos y siguientes pasos seguros

1. **P0 — Declaraciones Partner:** confirmar el cambio de estado observado (primero “No necesita PCD”, luego “Solicitud de acceso ... completada”) y reconciliarlo con PCD aún `Borrador`/no aprobado. Revisar cada “Sí” con el responsable; no marcar el AI self-review como completado.
2. **P0 — Controles PCD Level 2:** demostrar separación de producción/pruebas, cifrado de backups, DLP, acceso de staff, contraseña y logging; retención/cifrado Level 1 también siguen sin evidencia suficiente. La infraestructura real necesita revisión autorizada y artefactos protegidos.
3. **P0 — Product sourcing:** corregir o retirar de forma autorizada la capacidad si el listing no puede cumplir 5.5.1/5.5.2. La opción de cambiar el listing no se ejecutó.
4. **P1 — Dashboard:** la lectura más reciente muestra la comprobación automática superada; conservar evidencia saneada y no confundirlo con revisión/aprobación. No se pulsó `Ejecutar` ni `Enviar a revisión` en esta sesión.
5. Solo preparar un envío cuando no queden fallos obligatorios conocidos y cada declaración esté respaldada. La publicación y solicitud PCD permanecen **sin enviar y no aprobadas**.

## Restricciones de esta ejecución

Se utilizó el navegador autenticado únicamente para leer páginas Partner. No se guardó el formulario, no se cambió la selección de campos o respuestas, no se pulsó “Marcar como completado”/“Enviar a revisión”, no se reintentó la comprobación remota, no se instaló/reinstaló la app y no se leyeron ni modificaron registros PCD de clientes. No se cambió código de producción.

**Fuentes oficiales descargadas con Shopify CLI:**

- [App Store AI self-review requirements](https://shopify.dev/docs/apps/launch/app-store-review/app-store-ai-self-review-requirements) — SHA-256 `8344cf11677e42569e83f4ca5c94317ead3abaece18ab3aae21c0f6cfc5488d0`.
- [Protected customer data](https://shopify.dev/docs/apps/launch/protected-customer-data) — SHA-256 `a3b2a674474756a0ef5d867a48427f8f6953a84fb4d254a616d86c6c7dbcfc0c`.
- [App Store requirements](https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements), [best practices](https://shopify.dev/docs/apps/launch/shopify-app-store/best-practices), [billing](https://shopify.dev/docs/apps/launch/billing) y [submit for review](https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review).
