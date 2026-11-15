# Matriz de regresiones Shopify — DIAGLOB

**Fecha:** 2026-11-15. **Tipo:** pruebas sintéticas sin efectos sobre tiendas o transacciones reales.

## Qué agregamos

| Dominio | Pruebas nuevas | Propiedad verificada |
|---|---|---|
| OAuth y dominios | `test_shopify_oauth_crypto_matrix.py` | Origen de autorización, parámetros firmados HMAC, integridad de grants expirables, scopes efectivos y cifrado/rotura de secretos |
| Transporte GraphQL | `test_shopify_graphql_transport_matrix.py` | Estados HTTP (401/402/429/5xx), timeout, datos parciales, acceso PCD, errores de scopes y datos JSON no válidos |
| Privacidad y replay | `test_shopify_privacy_pilot_contract_matrix.py` | Identificadores, límites de selectores, payload allowlist, deduplicación de entregas, piloto bloqueado sin ámbito/credenciales |
| Pedidos y webhooks | `test_shopify_order_webhook_integrity_matrix.py` | Firma del cuerpo exacto, rechazo de manipulación, importe decimal finito, timestamps, estados, cantidades, direcciones acotadas |
| Existente y preservado | `test_shopify_checkout_reference_safety.py` y suites Shopify existentes | Rechazo de marcadores falsificados, idempotencia, aislamiento, billing, instalación administrada y privacy intake |

## Correcciones defensivas asociadas

- El cliente Admin GraphQL debe devolver un objeto `data` o lanzar error controlado; no aceptar `null`/listas como éxito.
- El parser de dinero de webhooks nunca deja pasar `NaN`, `sNaN` ni infinito a importes persistidos.
- No se modifica la lógica de aprobación de pagos, la ejecución de borrado real, los scopes de OAuth, ni la configuración de Shopify Partner.

## Ejecución

El workflow manual `.github/workflows/shopify-synthetic-contracts.yml` ejecuta una batería enfocada backend, más `npm test` y build frontend, sin secretos de producción. Adjunta resultados JUnit durante 14 días.

Comprobación por PR: `.github/workflows/validate-pr.yml` ejecuta regresiones backend completas en shards y build/tests frontend. Exigir CI del **head exacto del PR** antes de fusionar.

Ejemplo local:

```bash
cd backend
python -m pytest -q tests/test_shopify_oauth_crypto_matrix.py tests/test_shopify_graphql_transport_matrix.py tests/test_shopify_privacy_pilot_contract_matrix.py tests/test_shopify_order_webhook_integrity_matrix.py
cd ../frontend
npm ci && npm test && npm run build
```

## Brechas que no puede certificar CI sintético

| Flujo real | Evidencia faltante | Issue |
|---|---|---|
| `customers/data_request`, `customers/redact`, `shop/redact` | Exportación/borrado efectivos con decisiones de retención, proveedores y backups (no basta recibir webhook) | #266 |
| PCD / scopes de Shopify | Aprobación en Partner y grants concedidos por la tienda de desarrollo | #267 |
| OAuth / App Bridge / selector | Instalación, reinicio, roles e incógnito con cuenta autorizada; capturas sin credenciales | #199 y #189 |
| App Pricing y billing | Trial, aprobación/rechazo, upgrade/downgrade, reinstalación y separación del canal Paddle | #148 |
| WhatsApp -> Shopify Checkout | Carrito/orden de prueba, invoice URL, checkout y webhook firmado con atribución única, nunca cobro ajeno | #299 |
| WhatsApp | WABA de prueba, consentimiento, ventana de 24h, firmas y estados de entrega | #210 |

**Importante:** pasar estas pruebas no equivale a aprobación App Store, cumplimiento legal ni confirmación de operación real. Las pruebas reales requieren entorno autorizado, credenciales acotadas, protección PII y autorización explícita antes de escrituras/cargos/borrados.
