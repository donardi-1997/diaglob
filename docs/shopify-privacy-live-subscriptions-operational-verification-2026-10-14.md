# Verificación operativa real de los webhooks obligatorios — 2026-10-14

## Evidencia que SÍ está comprobada

- El despliegue a producción de commit `03c729a` terminó con éxito: https://github.com/donardi-1997/diaglob/actions/runs/38583961381
- Las migraciones de privacidad `b0c1d2e3f4a5`, `c0d1e2f3a4b5` y `d0e1f2a3b4c5` fueron ejecutadas en PostgreSQL y el estado de Alembic confirmó `d0e1f2a3b4c5 (head)`.
- El endpoint HTTPS `POST /api/webhooks/shopify/compliance` rechazó una firma HMAC falsa (HTTP 401) en producción.
- Las pruebas aisladas cubren firmas HMAC, los tres temas, deduplicación, transacción atómica, reintentos, cola de diez tareas y protección de PII.
- El nuevo paso de CI efectúa **tres** sondas HMAC inválidas y ejecuta un informe **de solo lectura** en la base productiva: `python -m app.shopify_privacy_operational_audit`. Solo expone sumas, valores booleanos y temas de Shopify fijos. No exporta emails, nombres, shop_id, store_id, tokens ni payloads.
- Un caso recibido, incluso con las diez tareas preparadas, **no significa una solicitud atendida**: la eliminación y la entrega real permanecen bloqueadas.

## Evidencia todavía FALTANTE, no declarar PASS

- No hay `shopify.app.toml` vinculado a la app de Diaglob en este repositorio.
- La auditoría productiva de GitHub Actions reportó **ausentes** `SHOPIFY_PARTNER_ORG_ID`, `SHOPIFY_PARTNER_APP_GID` y `SHOPIFY_PARTNER_ACCESS_TOKEN`. La ausencia de acceso desde Diaglob **no prueba** que Shopify carezca de suscripciones, solo impide comprobarlas por esa vía.
- Sin acceso a la **versión activa en Shopify Dev Dashboard**, los tres temas obligatorios siguen siendo **NO VERIFICADOS**, aunque el backend esté desplegado.
- No se ha realizado una entrega HMAC válida real de Shopify de cada tema ni comprobado su persistencia en producción; **no inventar una entrega sintética firmada que pudiera registrarse como caso auténtico en la base productiva**.
- No hay entrega segura de datos de acceso ni borrado real con excepciones legales y confirmaciones de proveedores.

## Validación pendiente en la aplicación EXISTENTE

1. Entrar a Shopify Dev Dashboard en la **aplicación Diaglob existente**, no crear otra aplicación. La documentación interna referencia app ID `416524435457`.
2. En **Versions** inspeccionar la versión **activa/liberada**. Bajo **Configuration → Webhooks**, confirmar exactamente estos tres temas y el destino HTTPS:
   - `customers/data_request`
   - `customers/redact`
   - `shop/redact`
   - `https://api.diaglob.tech/api/webhooks/shopify/compliance`
3. Si falta la configuración, utilizar el proyecto CLI ya vinculado a esa app o ejecutar `shopify app config link` para vincular la **misma** app; comparar Client ID, URL, embedded mode, OAuth redirects, scopes y versión de API. No fabricar un TOML nuevo con valores supuestos.
4. Añadir exactamente una vez la configuración de tres temas al TOML vinculado, auditándolo primero con:
   ```toml
   [[webhooks.subscriptions]]
   compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
   uri = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
   ```
5. Tras comprobar el entorno y con autorización del propietario de la app, ejecutar `shopify app deploy` y confirmar que **esa versión** quedó publicada/activa. La plantilla local no prueba una suscripción viva.
6. Ejecutar la verificación automática de Shopify y probar el transporte. `shopify app webhook trigger --api-version=2026-07 --address=https://api.diaglob.tech/api/webhooks/shopify/compliance --topic=<topic>` sirve para una prueba de entrega **de muestra** según Shopify, pero **no prueba que esté suscrito el evento** ni que la solicitud real de privacidad haya sido cumplida. Para garantizar aislamiento, realizar primero esta prueba con destino no productivo y base sintética o ambiente de staging.
7. Verificar el informe operativo agregado en la siguiente ejecución de **Deploy Production**, o ejecutar manualmente el auditor bajo un acceso seguro de solo lectura. Si se muestra `receipt_total: 0`, esto significa **cero casos registrados**, no “webhooks aprobados”. Si `receipts_missing_complete_ten_item_queue > 0` o `active_suppressions > 0`, investigar antes de activar cualquier tratamiento.
8. Revisar casos reales siguiendo la política de retención aprobada, con control de terceros, reingesta, respaldos y evidencias; no activar borrado sin esa autorización.

Documentación oficial:
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/build/webhooks/subscribe
- https://shopify.dev/docs/apps/build/cli-for-apps/app-configuration
- https://shopify.dev/docs/api/shopify-cli/app/app-webhook-trigger
