# DIAGLOB — Shopify Protected Customer Data: pregunta 10 (copias de seguridad cifradas)

**Revisión:** 20-oct-2026. **Estado:** NO ACREDITADO; mantener `No` para esta pregunta si se guarda el formulario sin evidencias adicionales. La ejecución de este plan requerirá aprobaciones independientes de almacenamiento, KMS, retención y restauración. No se ha creado ningún backup ni accedido al contenido de PostgreSQL.

**Pregunta Partner:** «¿Cifras tus copias de seguridad?». La respuesta `Sí` debe respaldarse con pruebas de cifrado de **todas las copias que contengan datos personales protegidos**, no solo con la presencia de un snapshot o el cifrado de un bucket distinto.

## 1. Evidencia AWS comprobada mediante API (solo metadatos)

| Recurso | Resultado observado | ¿Demuestra copia cifrada y recuperable de PostgreSQL? |
| --- | --- | --- |
| Lightsail `diaglob-prod` (us-east-2) | `AutoSnapshot` = **Enabled**, 07:00 UTC | No: solo configuración |
| GetAutoSnapshots | **0** puntos automáticos disponibles según API | No; verificar ejecución después de próxima ventana |
| GetInstanceSnapshots | 1 manual, `available`, `diaglob-prod-pre-release-20261015` | No: no se comprobó cifrado/restauración/consistencia DB |
| AWS Backup | 0 recursos protegidos y 0 trabajos recientes consultados | No demuestra un backup de instancia Lightsail o PostgreSQL |
| RDS | Sin instancias en la cuenta/región consultadas | La aplicación usa otro origen de DB; no se inspeccionó |
| S3 `diaglob-knowledge-765761474007-us-east-2` | SSE-S3 `AES256` por defecto; versionado activo | **No**: este bucket de conocimiento no es un destino de backup PostgreSQL verificado |

Los metadatos de Lightsail no proporcionan por sí solos una prueba completa de la configuración criptográfica del volumen raíz, de claves gestionadas, o de los bytes reales de una copia PG. No atribuir automáticamente a snapshots de instancia las propiedades documentadas específicamente para **discos de almacenamiento en bloques adjuntos**.

Fuente AWS: https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-configuring-automatic-snapshots.html , https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-snapshots.html .

## 2. Prioridades de implementación (NO ejecutadas)

### A. Verificar primer snapshot y proteger la recuperación

1. Tras el horario programado **07:00 UTC**, releer `GetInstance` y `GetAutoSnapshots`. Exigir registro con fecha, estado satisfactorio y origen `diaglob-prod`. Hasta entonces, aviso `LIGHTSAIL_AUTOSNAPSHOT_ENABLED_NO_SNAPSHOT`.
2. Conservar intacto el snapshot manual existente hasta confirmar otro punto y una ruta de recuperación. **No borrar snapshots como parte de esta auditoría.**
3. Definir el objetivo de recuperación (RPO/RTO) y responsables. Lightsail retiene solo los últimos siete snapshots automáticos; la política debe contemplar recuperación después de períodos más largos cuando aplique.
4. Planear prueba de restauración **en infraestructura aislada**, con servicios salientes/pagos/webhooks/notificaciones deshabilitados, acceso controlado y sin exponer datos PCD en cuentas o ambientes de desarrollo. Probar integridad y luego sanitizar/destruir la copia siguiendo procedimiento aprobado. **No se ha ejecutado la prueba.**

### B. Backups independientes y cifrados de PostgreSQL

**Antes de habilitar en producción, aprobar:**
- Destino dedicado de backups **fuera del servidor Lightsail** y distinto del bucket de conocimiento, con acceso público completamente bloqueado y prohibición de conexiones inseguras.
- Cifrado **SSE-KMS** en S3 con clave aprobada, políticas IAM mínimas de escritura/lectura por roles diferentes y auditoría de acceso a clave/objetos. No exponer claves ni contraseñas de DB en scripts o logs.
- Estrategia de rotación de claves, retención por clase legal y backups versionados; excepciones legal hold, tratamiento de `customers/redact`, y conciliación de tombstones tras restaurar.
- Horario de `pg_dump --format=custom` y monitoreo de estado/checksum/tamaño cifrado (sin metadatos personales). Preferir **streaming** con TLS a destino para evitar temporales en texto claro, control de `pipefail`, salidas no verbosas y alertas sin PCD. No asumir consistencia equivalente a recuperación continua (PITR).
- Procedimiento aislado para verificar que `pg_restore` puede leer y restaurar el archivo con versiones compatibles, roles mínimos y **sin reactivar tráfico externo**. Preferir fixtures sintéticos para pruebas recurrentes, y ejercicio con copia real solo en enclave de recuperación aprobado.

**Diseño ilustrativo — NO EJECUTAR sin destino, KMS, IAM, retención y credenciales aprobadas:**

```bash
# Ejecutar solo en host autorizado, con IAM role y PG* seguros precargados.
# No copiar secrets en comandos, scripts, logs o GitHub Actions.
set -o errexit -o nounset -o pipefail
: "${DIAGLOB_BACKUP_BUCKET:?}"
: "${DIAGLOB_BACKUP_KMS_KEY_ID:?}"
: "${PGDATABASE:?}"
# pg_dump usa PGHOST/PGUSER/PGPASSFILE o servicio de credenciales autorizado.
pg_dump --format=custom --no-owner --no-privileges --dbname="$PGDATABASE" |
  aws s3 cp - "s3://${DIAGLOB_BACKUP_BUCKET}/postgres/approved-prefix/backup-$(date -u +%Y%m%dT%H%M%SZ).dump" \
    --sse aws:kms --sse-kms-key-id "$DIAGLOB_BACKUP_KMS_KEY_ID" --no-progress
```

Este ejemplo **solo ilustra** formato y flujo: no incluye verificación criptográfica `head-object`, auditoría de KMS, comprobación de duración, metadata de checksum, ni prueba de restore. Antes de automatizarlo se debe implementar todo ese control y evitar credenciales de larga duración. `pg_dump` puede bloquear/impactar la carga; probar primero en una réplica/sandbox **sin PCD real**.

### C. Verificación del cifrado y custodia de claves

Para cada punto de backup nuevo, recopilar **metadatos saneados**:
1. `HeadObject` confirma `ServerSideEncryption=aws:kms` y referencia a la KMS **aprobada**, sin copiar el objeto ni exponer su contenido.
2. IAM/bucket/KMS niegan pública lectura, conexiones no TLS, acceso de tenants y operadores no autorizados. Comprobar quién puede exportar/descifrar.
3. Evidencia de ejecución de job sin fallas, manifest/checksum validado, y restauración con resultado OK a entorno aislado; fecha, versión PG, tiempo y revisor.
4. Registro de retención, expiración, excepciones y gestión de datos restaurados, incluidas solicitudes de privacidad.
5. No registrar emails, teléfonos, direcciones, SQL dump, secretos, claves, URLs presignadas, ni conexión DB en evidencia o issues.

## 3. Gate para declarar «Sí» en Shopify

**`Sí` SOLO SI:** existe al menos un backup PG independiente cifrado verificado con claves y acceso restringidos, la política de continuidad y restauración está vigente y probada, y **todos los demás destinos de backups con PCD también están cifrados y cubiertos**. Retención, test/prod y respuesta a incidentes tienen gates propios; la pregunta 10 no los sustituye.

**`No` mientras:** solo se vea AutoSnapshot Enabled; cero puntos automáticos; cifrado SSE de bucket ajeno; snapshot manual sin evidencia de protección y restauración; o no se conozcan backups extra/servicios de terceros.

**Pendiente de aprobación:** destino backup, clave KMS, roles y política, retención, costo, restauración y dueño operativo. No se crearán buckets, claves KMS, cron jobs o instancias adicionales con esta PR.

Referencia del auditor: `python -m tools.diaglob_aws_privacy_audit --region us-east-2 --instance diaglob-prod --bucket diaglob-knowledge-765761474007-us-east-2`. El auditor **nunca** lee PCD ni declara la pregunta 10 satisfecha.
