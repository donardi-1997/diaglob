# Shopify GDPR — vigilancia operativa P0 (2026-10-23)

**Estado:** implementado como monitor de solo lectura; **NO** es exportación,
borrado, cumplimiento del GDPR ni autorización de despliegue de un procesador
destructivo. Issue de implementación de privacidad: #266.

## Política de escalación implementada

Shopify requiere que las acciones de `customers/data_request`,
`customers/redact` y `shop/redact` se completen dentro de los 30 días
de la notificación, salvo información que deba conservarse legalmente.
Una excepción exige decisiones de retención documentadas, no un `200 OK`.

- `D+23`: advertencia si hay solicitudes con 23 días o más desde recepción.
- `D+30`: crítica; se cuenta toda solicitud no acreditada aunque el estado
  local diga `completed`.
- **Crítica inmediata** por tienda/organización no resuelta, tipo de webhook
  desconocido, hora de recepción futura o ausente, faltante de auditoría
  `shopify_hmac_verified`, cola de trabajo incompleta, ausencia de
  `processing_prepared`, marcado `completed` no verificado, o credenciales
  esenciales de HMAC/cifrado ausentes.
- Las consultas solo cuentan filas por metadatos. No recuperan payloads
  cifrados, emails, teléfonos, shop IDs, direcciones ni tokens; los logs
  muestran contadores globales, no IDs de solicitudes.
- El estado normal de la vigilancia **no** significa que la app esté lista
  para Shopify. `privacy_release_ready=false` es invariable.

## Ejecución

`python -m app.shopify_privacy_sla_watch` con el entorno del backend cargado.

- Código `0`: vigilancia sin alertas (sin evidencia de cumplimiento).
- Código `2`: alertas de vencimiento, cobertura o integridad.
- Código distinto de `0` por excepción: fallo técnico de vigilancia;
  **no suprimir** alertas de operación.

El workflow `.github/workflows/shopify-privacy-sla-watch.yml` ejecuta
el monitor cada seis horas, manualmente y después de modificar el workflow
en `main`. Se conecta por SSH a la instancia de producción, carga
`/etc/diaglob/diaglob.env`, ejecuta exclusivamente SQL de lectura y
utiliza los secretos existentes de Telegram para avisar si falla la tarea.
Si Telegram no está configurado, GitHub Actions conserva el estado fallido;
no se registra PII en el mensaje. Revisar tanto `Actions` como el canal
operativo.

## Lo que falta antes de declarar cumplimiento Shopify

1. **A1**: cerrar el inventario campo a campo de clientes compartidos,
   pedidos, conversaciones, agentes, archivos/S3, automatizaciones,
   proveedores, logs, respaldos y datos derivados. La cobertura actual
   sigue parcial; verificar aislamiento real por organización/tienda/sujeto.
2. **A2**: aprobar por responsable legal los periodos por jurisdicción,
   excepciones contables, holds, procesadores y su SLA. No deducir el
   periodo de retención de los 30 días de Shopify.
3. **A4**: implementar exportación COMPLETA en producción con selector
   firmado, enumeración de fuentes, protección de secretos, entrega
   autenticada y cifrada a destinatario del comercio y auditoría de
   descarga/purga; la función actual es parcial o sintética.
4. **A5–A6**: implementar redacción real, por tienda y sujeto, reversible
   solo según política aprobada, sin borrar clientes compartidos ni
   registros contables protegidos, y con tombstones que impidan reingesta.
5. **A7**: demostrar eliminación o bloqueo por proveedor, backups,
   restauración y control de reintroducción, con evidencias externas
   auténticas y plazos de supresión.
6. **A8**: ejecuciones completas con fixtures aislados, HMAC incorrecto,
   duplicados, reintento, cambio de organización, holding legal, proveedor
   caído, restore y pruebas operativas autorizadas. No utilizar PII de
   producción ni borrados destructivos como pruebas.

Mientras estas decisiones no existan, las implementaciones actuales
`shopify_privacy_synthetic_*`, `shopify_privacy_secure_delivery`
y `shopify_privacy_processing` deben seguir cerradas a cambios de datos reales.

Fuentes oficiales:

- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/build/webhooks/subscribe
