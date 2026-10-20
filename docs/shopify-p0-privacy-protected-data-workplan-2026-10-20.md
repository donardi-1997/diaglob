# DIAGLOB — Plan de cierre P0: privacidad y datos protegidos de Shopify
**Fecha:** 2026-10-20 · **Referencia:** PR #265 / evaluación de `main` en `fc8baf1`  
**Estado:** plan propuesto, no ejecutado. No autoriza cambios en producción ni cambios en Shopify Partner.

## Objetivo y restricciones
Cerrar de forma demostrable **P0-A: atención completa de solicitudes de privacidad de Shopify** y **P0-B: declaración y uso mínimo de datos protegidos de clientes**. El criterio de salida no es solamente pasar un test estático ni poner una casilla en verde, sino conseguir un flujo reproducible, seguridad por tenant/shop y evidencia actual de Shopify Partner.

Se trabajará con **datos sintéticos, base de datos aislada y tienda Shopify de desarrollo**, sin migrar aún la instalación de producción a staging. No pedir, exportar ni imprimir credenciales/PII en PR, chat o logs. La activación en producción se programará aparte, tras QA, revisión legal y aprobación del operador.

### Requisitos regulatorios/plataforma verificados
- Todos los public apps requieren `customers/data_request`, `customers/redact` y `shop/redact` y HMAC inválido ⇒ HTTP 401. Una respuesta 2xx confirma recepción válida, **no prueba** exportación/borrado. La acción aplicable debe completarse **dentro de 30 días** del webhook; las obligaciones legales de conservación son una excepción que debe revisarse y documentarse.
- `shop/redact` se emite típicamente **48 horas después de desinstalar**; no equivale al webhook `app/uninstalled`.
- Nivel Shopify PCD 0: ningún dato de cliente; nivel 1: datos de cliente sin nombre/dirección/correo/teléfono; nivel 2: esos campos identificatorios. Los public apps requieren revisión de nivel 1/2; nivel 2 exige medidas adicionales y selección de **cada campo necesario**. No dar por hecho que el scope `read_orders` implica automáticamente cuatro campos aprobados.
- Fuente Shopify: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance y https://shopify.dev/docs/apps/launch/protected-customer-data ; scopes mínimos: https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements .

## Decisión de alcance — al final del Día 3
**Opción recomendada para esta release:** conservar únicamente operaciones Shopify que se puedan demostrar como funcionales y necesarias. Si necesita leer nombre, teléfono, dirección o correo desde Shopify, **solicitar nivel 2 únicamente para esos campos**. Si alguna función no requiere datos de cliente, retirarle los scopes/campos sobrantes. Las operaciones de escritura que usan datos que ya aporta el comerciante deben clasificarse por separado de las lecturas desde Admin API.

**Condición de cambio:** No alterar scopes activos ni aprobación Partner hasta cerrar inventario de funcionalidades, revisar qué pasará con merchants existentes y preparar reautorización y rollback. No falsear «no necesita datos protegidos» para avanzar el checklist.

## Frente P0-A — privacidad / fulfillment real

| ID | Tarea y módulos iniciales | Responsable sugerido | Esfuerzo indicativo | Aceptación verificable |
|---|---|---|---|---|
| A1 | Inventariar los datos Shopify y sus flujos (origen, tabla/columna, tenant/shop/customer/order, destinatario y retención) en SQL, conversaciones, agentes/AI, automatizaciones, archivos S3, índices/KB, logs, colas y conectores efectivamente habilitados. Revisar `shopify_privacy_inventory_coverage.py`, `shopify_privacy_field_coverage.py`, `shopify_privacy_case_assessment.py`. | Backend + responsable de datos | 2–4 días | Matriz de cobertura sin superficies «desconocidas» y con registro explícito de no-aplica. |
| A2 | Aprobar política de retención, excepciones legales por registro y órdenes de borrado; asignar responsables de proveedores y respaldos, plazos de eliminación, respaldo y respuesta al comerciante. | Responsable de negocio / asesor legal + backend | 1–3 días, solapable | Política firmada; cada familia de datos tiene retención, base/propósito, borrado y tratamiento de respaldo documentados. |
| A3 | Consolidar máquina de estados de solicitud `received → verified → scoped → approved → executing → completed/partial/blocked`, trazabilidad sin PII, unicidad/idempotencia, retries, alertas por antigüedad y bloqueo de estados falsos. Revisar `shopify_compliance_webhooks.py`, `shopify_privacy_processing.py`, `shopify_privacy_review_workflow.py`. | Backend | 2–3 días | Firma errónea=401; persistencia fallida≠2xx; duplicado no duplica trabajo; fallos de proveedores nunca generan «complete». |
| A4 | Implementar exportación **real** `customers/data_request`, restringida al shop/shop ID firmado y sujeto autorizado, incluyendo `orders_requested` y casos sin customer ID. Completar contenido de fuentes realmente aplicables y entrega cifrada a un destinatario comerciante autenticado. Revisar `shopify_privacy_scoped_extraction.py`, `shopify_privacy_secure_delivery.py`. | Backend | 3–5 días | Export de prueba contiene datos correspondientes al shop/sujeto y ningún registro ajeno; descarga de un solo uso y TTL; auditoría de entrega, expiración y revocación. |
| A5 | Implementar `customers/redact` real: supresión/borrado o retención legal acotada de campos, derivados e índices; registrar órdenes afectadas, revocar acceso y evitar reingestión desde Shopify, colas o backup. Revisar `shopify_privacy_local_processor.py`, `shopify_privacy_suppression.py`, `shopify_privacy_restore.py`. | Backend | 4–7 días | Borrado selectivo probado en fixtures multi-tenant; caso con legal hold no destruye registro obligatorio y no se marca falsamente completo; reimportación bloqueada. |
| A6 | Implementar `shop/redact` tras desinstalación: eliminar datos de **esa tienda Shopify**, no toda la organización DIAGLOB, y limpiar fuentes, vinculaciones, credenciales, entregas y copias dentro de la retención aplicable. | Backend + infra | 2–4 días | Shop A purgado sin afectar Shop B; reinstalación o eventos tardíos no reactivan datos borrados ni cruzan merchants. |
| A7 | Completar tratamiento de proveedores externos, logs, S3/KB, backups y colas; registrar acuses y errores; procedimiento de restauración que reaplique tombstones. No declarar finalizado con un simple envío a proveedor. | Backend + infra + legal | 3–6 días | Matriz de procesadores firmada, evidencias de borrado/retención y prueba de restore/replay sin resucitar datos. |
| A8 | Operación y seguridad: cola de casos con responsables, alertas antes del plazo de 30 días, reparación/retry, aprobación doble para acciones irreversibles, reporte sin PII. | Backend + QA | 1–3 días | Operador detecta bloqueos y reintenta; acceso RBAC; evidencia auditable sin exponer identificadores protegidos. |

**Principios arquitectónicos:** usar datos tipados y scopes de `shop_id` + tenant + customer/order, jamás email como única clave; no reutilizar un estado «completado» en casos parcialmente resueltos; deduplicación estable para reintentos; respuestas de webhook rápidas con persistencia durable; acciones irreversibles tras verificación legal/operativa; cifrado de cualquier artefacto o selector sensible. Cada downstream no disponible deja un estado revisable/pendiente, no una falsa eliminación.

## Frente P0-B — protected customer data (PCD)

| ID | Tarea y módulos iniciales | Responsable sugerido | Esfuerzo indicativo | Aceptación verificable |
|---|---|---|---|---|
| B1 | Matriz **operación Shopify ↔ campo ↔ propósito ↔ origen ↔ almacenamiento ↔ feature**. Inspeccionar consultas GraphQL, webhooks, sync, `shopify_orders.py`, `shopify_cod_orders.py`, `shopify_fulfillment.py`, `shopify.app.toml` y la ruta embedded. Separar lectura de Shopify de escritura de datos aportados directamente a DIAGLOB. | Backend | 2–3 días, paralelo A1 | Cada dato solicitado se justifica y las 8 scopes actuales tienen racional de producto. |
| B2 | Decisión formal nivel 0/1/2, eliminación de scopes/campos no indispensables y definición de funciones Shopify que pueden fallar/deshabilitarse si no hay permiso. | Líder técnico + producto | 1 día | Tabla definitiva por scope y campo, sin solicitar acceso «por si acaso»; plan de reautorización/reversión. |
| B3 | Controles técnicos de PCD: cifrado y llaves, permisos por tenant/rol, acceso mínimo a empleados, registro de accesos sin PII, seguridad de backups, separación test/producción, estrategia de incidentes, retención y minimización de datos en logs, prompts/AI y analítica. | Backend + infra / seguridad | 3–5 días | Evidencia comprobada de Level 1 y, si aplica, Level 2; acceso denegado a personal sin permiso y test de logs/backup. |
| B4 | Adaptar GraphQL, UI y workflows a datos redactados por Shopify o no aprobados (incluidos `errors` HTTP 200 y campos `null`). No sustituir por registros de otra tienda o correo coincidente. | Backend + frontend | 1–3 días | Fixtures de permisos parciales y negados muestran errores controlados, sin fugas ni activación insegura de la feature. |
| B5 | Completar **Partner Dashboard → App → API access requests → Protected customer data access**, campos estrictamente necesarios, razones operativas, medidas de protección y disclosure/Privacy Policy. | Propietario Partner + responsable legal | 1–2 días, condicionado | Capturas de campos solicitados, solicitudes guardadas, estado visible (pendiente/aprobado) y textos consistentes con el código; no afirmar aprobación antes de Shopify. |
| B6 | Revalidar en tienda de desarrollo los campos aprobados, la versión activa, scopes realmente concedidos y el comportamiento en instalación/reautorización. | QA + operador Partner | 2 días | Evidencia de respuestas GraphQL permitidas/restringidas, grants vigentes y flujo funcional; nivel PCD aprobado si corresponde para el lanzamiento público. |

**Importante:** la captura actual «No necesita acceso a datos de clientes protegidos» se considera una **inconsistencia por verificar** con el consumo real del código, no prueba concluyente de ausencia o presencia de autorización. Primero completar B1/B2 y luego corregir la declaración sin mentir ni sobrepedir campos.

## Plan de calendario sugerido
**Horizonte:** 4 a 6 semanas de calendario, trabajo en paralelo con 1–2 desarrolladores backend, apoyo de frontend/infra/QA y validación legal/propietario Partner. **Estimación orientativa;** puede aumentar por brechas reales de inventario, dependencias de proveedores, respaldo o tiempos de aprobación Shopify.

| Ventana | Entregables y puertas |
| --- | --- |
| Semana 1 | A1+B1 inventario conjunto, A2 política, B2 decisión nivel y scopes. **Gate G1:** ninguna fuente o permiso crítico sin dueño, propósito y acción. |
| Semana 2 | A3 máquina de estados/auditoría, A4 exportación y B3/B4 controles PCD. **Gate G2:** export seguro y datos parciales probados en entorno aislado. |
| Semana 3 | A5/A6 redacción y purge por tienda, anti-reingestión, revisiones de retención. **Gate G3:** suites multi-shop y legal hold verdes. |
| Semana 4 | A7/A8 proveedores, backups, seguridad operativa; QA exhaustiva. Tramitar B5 tan pronto B1/B2/B3 estén firmes. **Gate G4:** evidencia por procesador y restauración. |
| Semana 5–6 (según revisión) | B6 pruebas Shopify development shop + reautorización, auditoría y despliegue controlado con rollback aprobado. Evidencia final, actualización de matriz y nueva evaluación Shopify AI Toolkit. **Gate G5:** cierre verificable de A y B y aprobación del dueño/seguridad/legal. |

## Pruebas de aceptación obligatorias
- **Firma/intake:** 401 HMAC inválido; webhook duplicado/reenviado; 2xx solamente tras aceptación durable; fallo BD/cola=respuesta reintentable; payload incompleto/fraudulento.
- **Aislamiento:** dos shops del mismo tenant, mismo email entre dos tenants, identidades no vinculadas, rotación/reinstalación Shopify; no filtración ni borrado transversal.
- **Acceso:** `customers/data_request` con IDs correctos, solo correo, `orders_requested` parcial, sujeto inexistente, permisos revocados, remitente comercial no autenticado.
- **Borrado:** `customers/redact`, `shop/redact`, eventos desordenados/duplicados, orden con legal hold, backups/restores, colas, logs e índices, proveedor externo caído.
- **PCD:** nivel 1/2 según decisión documentada; campos no aprobados `null` + `errors` GraphQL incluso con HTTP 200; minimización visible; test de permisos/roles; sin PII en logs o alertas.
- **E2E:** callbacks firmados, tienda de desarrollo, comprobación de suscripciones de la **versión activa** en Shopify; la simulación vía CLI no demuestra por sí sola que el registro esté desplegado.
- **QA/evidencia:** tests unitarios + integración + smoke de rollback sobre commit final, sin datos reales; tabla de resultado, SHA y capturas sin secretos.

## Definition of Done / restricciones de entrega
**P0-A cerrado** solo cuando los tres eventos ejecutan la acción aplicable conforme a política legal (o excepción documentada), cubren datos propios y procesadores, no reimportan datos y aportan evidencias verificables de entrega/borrado dentro del SLA. El código heredado con `fulfillment_complete=False` requiere actualización **con respaldo real de estado**, nunca un cambio cosmético de booleano.

**P0-B cerrado** solo cuando Partner refleja la declaración exacta para el nivel real de datos y los campos mínimos, el acceso está aprobado para producción pública cuando aplique, la implementación cumple sus controles y la app tolera campos no permitidos sin fugas ni fallos críticos.

**Publicación:** cerrar A y B **no equivale** a App Store ready; el flujo de instalación/reinstalación, App Pricing, cuenta del revisor y evaluación oficial siguen siendo puertas separadas del PR #265. No fusionar ni desplegar este plan como si implementara las soluciones.

## Primer bloque de trabajo propuesto
1. Construir la matriz B1/A1 compartida desde modelos y operaciones, marcando datos de Shopify, datos agregados por DIAGLOB y terceros.
2. Auditar los ocho scopes presentes en `shopify.app.toml` y diferenciar operaciones de lectura y escritura; decidir campos nivel 1/2.
3. Determinar exactamente qué capas de privacidad siguen bloqueadas y qué se puede habilitar únicamente en fixtures sintéticos.
4. Obtener visto bueno de negocio/legal sobre conservación, external processors y backups.
5. Solo entonces implementar A3–A8/B3–B6 en ramas de ingeniería pequeñas, con revisiones independientes.

**Responsabilidades propuestas (sin asignación personal):** líder backend = A1/A3–A8/B1/B4; infra/seguridad = cifrado, respaldos y accesos; responsable de producto/Partner = B2/B5; legal/privacidad = A2; QA = todas las pruebas y evidencia. El propietario aprueba cualquier modificación irreversible de producción.
