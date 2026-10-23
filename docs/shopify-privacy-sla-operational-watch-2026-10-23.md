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
  desconocido, ausencia de `DIAGLOB_INTERNAL_SECRET` cuando existen solicitudes
  pendientes, hora de recepción futura o ausente, faltante de auditoría
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
el monitor cada seis horas, manualmente y después de que el workflow `Deploy Production` finalice
con éxito en `main`. Nunca inicia el primer audit desde el evento de push,
pues el módulo podría no estar desplegado todavía. Se conecta por SSH a la instancia de producción, carga
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

## Verificación de infraestructura AWS (read-only, 2026-10-23)

Comprobación puntual de AWS us-east-2, **no** auditoría de todos los
servicios/cuentas/regiones y **no** prueba de una política legal aprobada.

| Recurso | Observado | Pendiente |
| --- | --- | --- |
| Lightsail `diaglob-prod` | Instancia en `running`, 3 snapshots automáticos visibles, 1 snapshot manual `pre-release` disponible | Acreditar periodicidad/retención, cifrado, destrucción, recuperación y prueba real de restauración |
| S3 `diaglob-knowledge-765761474007-us-east-2` | `AES256` por defecto, versionado `Enabled`, cuatro controles de bloqueo de acceso público `true` | Faltan revisión de permisos IAM, de lectores/autorizaciones, trazabilidad de objetos y restauración |
| S3 lifecycle | `NoSuchLifecycleConfiguration` al consultar el bucket conocido | No existe una regla de lifecycle configurada para versiones/objetos en ese bucket; aprobar periodos antes de implementar, sin purgas automáticas arbitrarias |

El versionado de S3 no es una garantía de borrado de datos personales;
eliminar la versión actual puede dejar versiones antiguas recuperables.
No se debe interpretar existencia de snapshots como evidencia de que las
copias siguen los tiempos legales o que DIAGLOB pueda reprimir la reingesta
después de restaurarlas. Abrir una decisión de retención/restore y documentar
el dueño responsable antes de habilitar borrado Shopify real.

**Observación de despliegue:** la primera ejecución automática por evento
`push` falló mientras producción todavía no había recibido el módulo
`app.shopify_privacy_sla_watch`. La corrección del workflow activa la
comprobación al finalizar con éxito `Deploy Production`, más el cron y
la ejecución manual. Ese fallo era un *race* de despliegue, no un caso GDPR.

## Diagnóstico concreto en producción (auditoría de despliegue #40000698508)

El reporte agregado de la aplicación del 23-oct-2026 mostró:

- 1 `shop/redact` HMAC-auditado; 0 `customers/redact` y 0 `customers/data_request` en ese corte. No se inspeccionaron datos identificatorios del merchant ni del cliente.
- 1 `processing_prepared` y 1 `received` de origen autenticado, 0 recibos con cola incompleta, 0 trabajos marcados completados falsamente. **Esto demuestra intake/cola, no erasure.**
- `data_export_or_erasure_fulfilled=false` y `privacy_fulfillment_release_ready=false`. Este `shop/redact` requiere clasificación, posible conservación mínima y ejecución/proveedores con evidencia.
- `internal_review_secret_present=false`. La API protegida por `DIAGLOB_INTERNAL_SECRET` no puede servir de consola de revisión con la configuración observada. La vigilancia lo considera un bloqueo crítico cuando hay recibos. No imprime ni modifica el secret ni abre ese acceso por defecto.

**Acción del operador autorizada pendiente:** establecer un secreto interno
largo en el archivo protegido, definir los operadores aprobados y comprobar
el acceso por un canal autenticado sin publicar el secreto en GitHub Actions
ni en chat. No desbloquear exportación o borrado real sin las autorizaciones
jurídicas y técnicas enumeradas arriba.
