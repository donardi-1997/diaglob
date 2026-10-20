# DIAGLOB — Matriz de aceptación Shopify App Store / tienda POC

**Fecha:** 2026-10-20. **Tienda:** `diaglob-poc.myshopify.com` (Shopify Basic App Development). **Aplicación:** DIAGLOB existente, Client ID público `c5fc9aed710462d41767477fa9e595c0`.

**Política de evidencia:** únicamente aprobaciones y pruebas ejecutadas cuentan como `PASS`. Se deben guardar resultados con fecha, versión Shopify, commit/backend, ejecutor, expectativas y enlaces a capturas saneadas. Los casos de venta/entrega usan datos ficticios de tienda de desarrollo y no generan cargos reales. No copiar tokens, datos de compradores, códigos de claim ni IDs de tickets privados al repositorio.

| ID | Frente | Acción controlada | Evidencia necesaria y criterio PASS | Estado 20-Oct |
| --- | --- | --- | --- | --- |
| S01 | Identidad | Consultar `appByKey` en tienda POC, misma app y dominio Shopify | `appByKey.apiKey` coincide y `installation` existe | **PASS** (solo metadata) |
| S02 | Versión | Inspeccionar versión activa y nueva candidata de app **existente** en Dev Dashboard | Identidad, URLs embedded, extensiones, tópicos GDPR y versión previas sin regresiones | **NO VERIFICADO** |
| S03 | Scopes requested | Consultar `requestedAccessScopes` de DIAGLOB | Exactamente los siete scopes de `SHOPIFY_SCOPES` | **FAIL**: Shopify solicita seis heredados |
| S04 | Scopes granted | Consultar `installation.accessScopes` después de abrir app y autorizar | Exactamente siete, sin `read_customers` ni `write_products` | **FAIL**: concedidos seis heredados |
| S05 | PCD Nivel 2 | En Dev Dashboard verificar selección y estado `Name, Address, Email, Phone` | Campos seleccionados/justificados conforme a necesidades reales, sin afirmaciones falsas de cumplimiento | **NO VERIFICADO** |
| S06 | Entrada embedded | Abrir DIAGLOB en Shopify Admin POC | App Bridge emite token de sesión válido y backend verifica tienda con identidad correcta | **SIN E2E** |
| S07 | Instalación managed | Cuenta merchant de prueba genera código de un solo uso y reclama tienda autorizada | Se vincula organización/tienda adecuada; código expira y replay falla | **SIN E2E** |
| S08 | Consentimiento scopes | Abrir app tras versión publicada y consentir permisos añadidos | Eventos y lecturas requested/granted coinciden; rechazo no concede información | **BLOQUEADO POR S02-S04** |
| S09 | Permiso PCD denegado | Con app de test en estado controlado sin aprobación, ejecutar consulta controlada | Error seguro `SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED` o campo `null`; no PII parcial ni log | **SOLO UNIT TESTS** |
| S10 | Scope revocado | Simular revocación con ciclo de reautorización oficial y operador | `SHOPIFY_SCOPE_DENIED`; sin acceso a operaciones que requieren scope | **SIN E2E** |
| S11 | Roles/tiendas | Acceder desde staff limitado a otra tienda de **la misma organización** | Respuesta 403/404, sin nombres, importes ni datos de tienda no asignada | **SOLO TESTS SINTÉTICOS** |
| S12 | Tenant cruzado | Dos organizaciones con clientes sintéticos de email coincidente | A no puede leer, actualizar o exportar B; vinculación explícita por Shopify ID/shop | **SOLO TESTS SINTÉTICOS** |
| S13 | Productos/pedidos | Leer y sincronizar objetos de prueba (sin comprador real) | UI consistente sin scopes no concedidos ni leaks; resultados correlacionados con tienda | **SIN E2E** |
| S14 | Fulfillment | Probar operación autorizada de merchant-managed fulfillment en tienda desarrollo | Solo tiendas/órdenes propias, idempotencia y scopes merchant-managed correctos | **BLOQUEADO POR S04** |
| S15 | Billing Shopify | Selección plan, cancelación, rechazo, reintento, renovación y reinstalación | Shopify-hosted billing; no Paddle para cuentas Shopify; sin cobros reales | **SIN E2E** |
| S16 | Compliance webhooks | Recibir `customers/data_request`, `customers/redact`, `shop/redact` reales y firmados | Tres tópicos en versión activa, HMAC comprobado, receipt idempotente y trazabilidad | **SIN E2E** |
| S17 | Fulfillment privacidad | Ejecutar expediente GDPR con identidad y tienda verificadas | Exportación, borrado/retención legal y comunicación completados sobre dataset sintético, incluyendo backups/proveedores | **BLOQUEADO**: aún no está habilitado cumplimiento real |
| S18 | Uninstall/Reinstall | Desinstalar POC, recrear autorización con usuario de prueba y reclamar tienda | Credenciales anteriores revocadas, no tiendas huérfanas, sin acceso cruzado | **SIN E2E** |
| S19 | Recovery y cifrado | Comprobar cifrado efectivo de DB/backups, logs de acceso y restore aislado | Evidencia operativa y política de retención aprobada; sin PII expuesta | **PARCIAL** |
| S20 | Envío App Store | Reconciliar Partner PCD, versiones, billing, permisos, privacidad y screencast | Todos los casos críticos anteriores PASS, matriz de autoevaluación sin bloqueos | **NO-GO** |

### Procedimiento mínimo para registrar pruebas

1. Capturar la versión exacta de DIAGLOB en Dev Dashboard y commit GitHub de su app/backend.
2. Antes de hacer mutaciones, guardar la lectura read-only de `appByKey` con scopes solicitados y concedidos. Herramienta local: `python -m tools.shopify_dev_store_scope_gate` (con token de desarrollo desde un gestor de secretos).
3. Preparar **solo datos de prueba** y usuarios Shopify/DIAGLOB con scopes deliberadamente limitados. No utilizar pedidos reales de Bakatá ni tiendas de comerciantes reales.
4. Ejecutar acciones positivas y negativas en la tienda de desarrollo; registrar código HTTP/estado, respuesta saneada, razón y evidencia de aislamiento entre usuarios/tiendas.
5. Para privacidad, demostrar el proceso completo sin limitarse al webhook/HTTP 2xx; auditar destinos externos, derivados, retención, backups, consentimiento y obligaciones legales.
6. Marcar `PASS` únicamente tras evidencia y revisión; un PR fusionado o una CI aprobada solo habilita el inicio de pruebas, no sustituye ejecución.
7. No avanzar a publicación App Store con S03, S04, S05, S16 o S17 sin validar ni cerrar formalmente. No copiar secretos ni información de consumidores a grabaciones de revisión.

### Estado real de fecha base

La única prueba de Shopify ejecutada directamente en esta revisión fue **metadatos de instalación y scopes de la POC** (S01, S03, S04). El resto se deriva de fuente y pruebas sintéticas; no se realizaron nuevas operaciones de instalación, checkout, GDPR real ni publicación Shopify.

### Evidencia y recursos

- Matriz PCD para Partner: `docs/shopify-pcd-partner-submission-evidence-2026-10-20.md`
- Scope audit live: `docs/shopify-diaglob-poc-live-scope-audit-2026-10-20.md`
- Guía de versionado seguro: `docs/shopify-managed-scope-release-runbook-2026-10-20.md`
- Tests: `backend/tests/test_shopify_dev_store_scope_gate.py`, `backend/tests/test_shopify_protected_access_denials.py`, `backend/tests/test_shopify_customer_access_scope.py`
- Documentación oficial: https://shopify.dev/docs/apps/launch/protected-customer-data y https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes

**Regla de aprobación:** NO-GO hasta evidencia externa y controles de Nivel 2. La matriz está diseñada para rechazar falsas declaraciones de completitud.
