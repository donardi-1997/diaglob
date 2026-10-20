# DIAGLOB — Verificación real de scopes en Shopify POC (2026-10-20)

**Resultado:** BLOQUEADO para prueba funcional completa y revisión de permisos protegidos. Se verificó información **directamente** en la Shopify Admin GraphQL API de la tienda conectada `diaglob-poc.myshopify.com` mediante la app Shopify autorizada del entorno POC. No se consultaron clientes, pedidos ni otros datos PCD. No se cambiaron apps, scopes, instalaciones, versiones, tokens ni configuraciones.

## 1. Evidencia obtenida

- Tienda conectada: `Diaglob POC`, dominio canónico `diaglob-poc.myshopify.com`, plan `Basic App Development`.
- Consulta GraphQL de solo lectura: `shop { myshopifyDomain }` y `appByKey(apiKey: <DIAGLOB_PUBLIC_CLIENT_ID>) { apiKey title handle requestedAccessScopes { handle } optionalAccessScopes { handle } installation { id accessScopes { handle } } }`.
- `appByKey` devolvió la aplicación DIAGLOB (`handle=diaglob`, `apiKey` coincidente) y una instalación no nula en esta tienda.
- `requestedAccessScopes` y `installation.accessScopes` devolvieron **exactamente los mismos seis scopes**, pero **no** coinciden con los siete que requiere el `main` consultado tras merge de PR #277 (`f455b48d`).
- `optionalAccessScopes`: conjunto vacío. Esta consulta no prueba PCD Nivel 1/2 aprobado, identidad de la versión liberada en Partner, políticas de retención, datos de clientes ni E2E del flujo de compra.

| Scope | `main` (OAuth + TOML) | Solicitado Shopify | Concedido tienda POC | Decisión |
| --- | :---: | :---: | :---: | --- |
| `read_products` | Sí | Sí | Sí | Conforme |
| `read_inventory` | Sí | Sí | Sí | Conforme |
| `read_orders` | Sí | Sí | Sí | Conforme |
| `write_orders` | Sí | Sí | Sí | Conforme |
| `write_draft_orders` | Sí | No | No | Falta liberar/autorizar |
| `read_merchant_managed_fulfillment_orders` | Sí | No | No | Falta liberar/autorizar |
| `write_merchant_managed_fulfillment_orders` | Sí | No | No | Falta liberar/autorizar |
| `read_customers` | No | Sí | Sí | Permiso heredado; retirar |
| `write_products` | No | Sí | Sí | Permiso extra; revisar/retirar |

**Diferencia real:** tres faltantes y dos adicionales respecto de `main`. Por lo tanto hay discrepancia tanto entre **código ↔ configuración solicitada Shopify** como entre **código ↔ grants concedidos**. No basta con ejecutar pruebas unitarias o fusionar PR de scopes.

## 2. Medida de seguridad implementada en este frente

`backend/tools/shopify_dev_store_scope_gate.py` proporciona un gate para una tienda autorizada mediante `appByKey`, **no** mediante `currentAppInstallation`, porque este último inspecciona solo la app propietaria del token y podría corresponder a un conector distinto de DIAGLOB.

Compara: identidad de tienda, clave pública de la misma app, `shopify.app.toml`, `SHOPIFY_SCOPES`, `requestedAccessScopes`, `optionalAccessScopes` y `installation.accessScopes`. Devuelve 0 solo cuando todos los conjuntos necesarios son exactos, sin permisos extra, y 2 por discrepancias. La falta de identidad/datos válidos falla en cerrado; jamás afirma aprobación PCD ni E2E.

Solo para un operador con token de **una app autorizada a consultar** metadatos de instalaciones en la tienda de desarrollo:

```bash
cd backend
# Configurar SHOPIFY_AUDIT_SHOP y SHOPIFY_AUDIT_ACCESS_TOKEN mediante
# variables privadas de entorno/gestor de secretos; nunca en Git o logs.
python -m tools.shopify_dev_store_scope_gate
```

No copiar el token a un ticket ni a un PR. La verificación mediante el conector Shopify ya dio el resultado anterior; **no** hemos ejecutado este nuevo CLI contra Shopify todavía. Sus tests utilizan fixtures sintéticos.

## 3. Próximas acciones verificables

1. En **la aplicación DIAGLOB existente** del Shopify Dev Dashboard, cotejar el identificador público de la app y la versión liberada. No crear una segunda app por accidente.
2. Determinar si la instalación se gestiona con Shopify-managed installation o flujo OAuth legado. Revisar la configuración de la versión vigente antes de publicar scopes.
3. Liberar una versión de la **misma** aplicación con los siete scopes correctos y confirmar las suscripciones a `customers/data_request`, `customers/redact` y `shop/redact`. La publicación debe seguir el flujo correcto Shopify CLI/Dev Dashboard; un merge en GitHub no actualiza automáticamente la versión de Shopify.
4. Abrir DIAGLOB desde Shopify Admin en `diaglob-poc.myshopify.com`; aceptar permisos añadidos si Shopify los solicita. Probar rutas sin permiso y rehabilitación según el flujo de la app. Para permisos reducidos, verificar revocación efectiva, no asumirla.
5. Volver a consultar `appByKey`, distinguir **solicitados** de **concedidos**, y exigir siete scopes exactos, sin `read_customers` ni `write_products`. Dejar evidencia saneada con versión y fecha.
6. Completar **por separado** solicitud Protected Customer Data Nivel 1/2 con justificación individual de nombre, correo, teléfono y dirección, según datos realmente tratados. Los scopes no sustituyen aprobación PCD.
7. Ejecutar E2E autorizado: instalación, App Bridge, reautorización, webhook firmado, permisos denegados, cliente de prueba sintético, aislamiento multitienda, desinstalación/reinstalación y privacidad; ninguna mutación de pedidos/pagos/fulfillment real sin aprobación expresa.

**Bloqueo actual:** release Shopify NO-GO. Los hallazgos no prueban que DIAGLOB tenga PCD concedido. Tampoco certifican que el flujo GDPR de exportación/borrado esté funcionando en producción.

Referencia oficial: https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes
