# DIAGLOB — Shopify mandatory privacy webhooks: reintentos, deduplicación y auditoría

**Estado:** fortalecimiento de la entrada firmada de Shopify. No habilita exportación, supresión, consentimientos ni cierre de obligaciones GDPR.

## Cambios

- Se mantiene la validación HMAC de `/api/webhooks/shopify/compliance` **sobre el cuerpo original**, antes de interpretar el JSON. El recibo cifrado, la evidencia de entrada y las diez tareas de revisión se crean en la misma transacción.
- Para entregas nuevas con `X-Shopify-Webhook-Id`, el identificador de recibo utiliza **solo la identidad global de esa entrega**, con espacio de nombres versionado. Así un reintento que cambie tema, tienda, shop ID, cliente o pedidos no obtiene otra clave idempotente; la comparación del recibo almacenado devuelve conflicto y no crea otra obligación.
- Para entregas históricas del formato anterior, la búsqueda conserva una **compatibilidad con la clave original**, además del nuevo formato. No se migran filas ni se reescriben recibos existentes. Si hay más de una coincidencia, se devuelve error y requiere revisión.
- La entrada sin encabezado de entrega conserva compatibilidad por hash de payload, **sin garantizar identidad individual**. La ausencia de `X-Shopify-Webhook-Id` debe seguir siendo visible como limitación operacional.
- Los reintentos ya **no devuelven 200 por encontrar simplemente diez filas**. Exigen auditorías `received` (actor HMAC verificado) y `processing_prepared`, el conjunto de áreas completo, acciones consistentes y ausencia de estados de falso cumplimiento.
- La recuperación de un recibo firmado sin tareas reconstruye las diez tareas y registra `processing_prepared` solo si faltaba, evitando evidencias duplicadas. Las colas parciales continúan bloqueadas.
- La auditoría operacional ahora señala tareas con estado `completed`, `fulfilled`, `delivered`, `deleted` o `erased` como anómalas: el flujo de supresión real no está autorizado.

## Compatibilidad y límites importantes

**Límite histórico:** recibos anteriores no almacenan la clave global derivada del ID de entrega. Una entrega antigua que altere simultáneamente los datos que formaban parte de la clave original podría no enlazarse con el recibo antiguo. La compatibilidad de reintentos **idénticos** está probada, pero una garantía global retroactiva requeriría un backfill controlado con evidencia original suficiente; **no deducir claves a partir de identidad conjeturada**.

**Shopify:** `X-Shopify-Webhook-Id` es un identificador único de entrega; `X-Shopify-Event-Id` correlaciona distintas entregas de una acción y **no** debe usarse para eliminar recibos separados. Referencia: https://shopify.dev/docs/apps/build/webhooks/verify-deliveries y https://shopify.dev/docs/apps/build/webhooks/delivery-structure.

**HTTP 200** confirma solamente recibo íntegro y revisión encolada. **HTTP 500** ante pérdida de evidencias obliga a investigación y permite reintentos de transporte; nunca declara exportación o eliminación completa. Los rechazos por HMAC inválido no crean datos. No hay llamadas a Shopify Admin o proveedores durante la transacción.

## Comprobación automatizada

```bash
cd backend
pytest -q tests/test_shopify_compliance_webhooks.py tests/test_shopify_privacy_processing.py tests/test_shopify_privacy_operational_audit.py
```

Se cubren (solo SQLite/fixtures sintéticos): duplicados, entrega global reutilizada con tienda/tema contradictorios, compatibilidad con recibo legado, evidencia de recepción o preparación eliminada, cola incompleta, estado falsamente completo, acción alterada, recuperación sin duplicar auditoría, HMAC y rollback transaccional.

**Antes de producción:** confirmar suscripciones en la versión activa de la app Shopify, pruebas válidas del proveedor sin datos reales, métricas de tiempos y fallos, y un plan auditado de rehabilitación de casos antiguos. Sin estas pruebas no se declara listo el cumplimiento Shopify.
