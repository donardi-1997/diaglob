# DIAGLOB — Plan verificable de recuperación y retención PCD

> **ACTUALIZACIÓN 20-oct-2026, posterior a la inspección inicial:** la instancia
> `diaglob-prod` ya muestra `AutoSnapshot=Enabled` a las 07:00 UTC.
> `GetAutoSnapshots` sigue devolviendo **0** puntos automáticos, y la
> instancia conserva 1 snapshot manual `available`. Los valores `Disabled`
> y «activación no realizada» que aparecen **más abajo** son registros
> históricos de la primera auditoría, **no el estado actual**.
> Las copias cifradas independientes de PostgreSQL, su control de claves y
> una restauración aislada aún no están verificadas.
> Seguimiento específico pregunta 10:
> `docs/shopify-pcd-question-10-encrypted-backups-2026-10-20.md`.

**Fecha de inspección:** 2026-10-20. **Región:** `us-east-2`. **Alcance:** lectura de metadatos AWS, auditor de código y borrador de una regla S3 **deshabilitada**. No se modificó la infraestructura ni se accedió a datos personales, archivos, claves ni snapshots.

## 1. Hallazgos de producción comprobados

| Componente / operación | Resultado observado | Riesgo o límite |
| --- | --- | --- |
| Lightsail `diaglob-prod`: `GetInstance` | `running`; `AutoSnapshot`: **Disabled**; hora que figuraba configurada: 07:00 UTC | Sin respaldo automático diario en esta instancia |
| Lightsail: `GetAutoSnapshots` | **0** copias automáticas | No hay restauración automática demostrada |
| Lightsail: `GetInstanceSnapshots` | 1 manual `available`: `diaglob-prod-pre-release-20261015`; creado 2026-10-15 13:58:20 UTC | Un solo punto manual, creado cinco días antes de la auditoría; no hay evidencia de restore |
| AWS Backup: `ListProtectedResources` | **0** recursos protegidos, respuesta no paginada | No aporta ruta de recuperación verificada para el servidor |
| AWS Backup: planes y bóvedas | 1 plan y 1 bóveda | La existencia de un plan no significa que esta instancia esté protegida |
| S3 `diaglob-knowledge-765761474007-us-east-2`: `GetBucketEncryption` | `AES256` | Cifrado del bucket sí; **no** se verificó cifrado del disco PostgreSQL ni respaldos de servidor |
| S3: `GetPublicAccessBlock` | Cuatro controles en `true` | Protección contra acceso público, no sustituye aislamiento IAM |
| S3: `GetBucketVersioning` | `Enabled` | Las versiones antiguas permanecen tras un borrado normal |
| S3: `GetBucketLifecycleConfiguration` | `NoSuchLifecycleConfiguration` | No se expiran versiones antiguas automáticamente |
| S3: `ListObjectVersions` (página íntegra) | 2 versiones antiguas y 2 delete markers; 0 objetos actuales en `ListObjectsV2` | **No** borrar versiones antiguas sin confirmar procedencia/retención legal |
| S3: `GetBucketLogging` | Ninguna configuración | Logs de acceso de S3 no configurados; no equivale a ausencia de CloudTrail |
| S3: `GetObjectLockConfiguration` | `ObjectLockConfigurationNotFoundError` | No se verifican legal holds por Object Lock |
| S3: `GetBucketReplication` | `ReplicationConfigurationNotFoundError` | No hay réplica S3 configurada en ese bucket |

**Evidencia negativa:** no se inspeccionó el filesystem de producción, `pg_dump`, WAL, cifrado del root filesystem, credenciales de PostgreSQL, cron/systemd, otras cuentas/regiones ni destinos alternativos. No afirmar que *no existe ningún backup* fuera de estas rutas AWS.

## 2. Prioridad P0 — respaldo automático Lightsail

1. Definir dueño de la recuperación, RPO/RTO, ventana operativa y techo de costo de almacenamiento. El add-on `AutoSnapshot` genera snapshots diariamente y conserva los últimos siete, con facturación de almacenamiento.
2. Habilitar el add-on sobre `diaglob-prod` solo tras autorizar ese costo y configuración; usar el horario apropiado en UTC. La configuración inspeccionada indicaba **07:00 UTC** aunque estaba deshabilitada. La activación no se ha efectuado.
3. Releer `GetInstance` y `GetAutoSnapshots`, verificando add-on `Enabled`, recurso correcto, estado `available` del punto y fecha. No marcar verificado mientras no exista la primera copia.
4. Prueba de restauración hacia **instancia aislada, no producción**: sin DNS público, secretos rotados, acciones externas/suscripciones desactivadas; registrar comprobaciones de integridad con **datos sintéticos**.
5. Incorporar además copia **coherente de PostgreSQL**: `pg_dump --format=custom` con cifrado, destino fuera de instancia, clave/roles restringidos, retención definida y restore controlado. Un snapshot de disco no demuestra consistencia de transacciones de la base de datos.
6. Probar borrado/exportación de datos sujetos a privacidad sin exposición por logs ni restauración de información suprimida. Registrar controles de replay/tombstones.

Referencia oficial: https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-configuring-automatic-snapshots.html

## 3. Prioridad P1 — S3 ciclo de vida con retención legal

No configurar una regla global sobre el bucket. Una regla `NoncurrentVersionExpiration` **elimina permanentemente versiones antiguas**, por lo que exige decisiones documentadas de retención, incluyendo datos de conocimiento, copias de objetos y medidas post-restauración.

Añadido `backend/tools/diaglob_s3_lifecycle_preview.py`, sin dependencia de boto3 ni operaciones AWS. Requiere un prefijo exacto de documentos de una KB de organización, plazo numérico explícito y referencia de aprobación. Genera únicamente un JSON de regla `Status=Disabled`, **no** toca el bucket y no se fusiona automáticamente con las reglas existentes. Los plazos de ejemplo no son propuesta legal.

```bash
cd backend
python -m tools.diaglob_s3_lifecycle_preview \
  --prefix organizations/1/knowledge-bases/8/documents/ \
  --noncurrent-days <PLAZO_APROBADO> \
  --approval-reference <REFERENCIA_AUTORIZADA>
```

Para implementar realmente, habría que revisar prefijos, Object Lock, datos versionados, flujos de reingesta, retención fiscal y excepciones, y obtener la autorización del responsable. Releer la configuración antes de cualquier `PutBucketLifecycleConfiguration` para no sustituir reglas existentes. **No hay aprobación registrada en este cambio.**

Documentación oficial:
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshooting-versioning.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html

## 4. Auditoría reproducible ampliada

El script existente `backend/tools/diaglob_aws_privacy_audit.py` ahora inspecciona:
- Lightsail: habilitación AutoSnapshot, cantidad de puntos, estado y fecha de snapshots manuales, sin afirmar prueba de restore.
- S3: cifrado por defecto, cuatro bloqueos públicos y estado de server access logging.
- AWS Backup: número de recursos protegidos (sin imprimir ARNs).
- Estado previo: lifecycle, versionado, versiones anteriores, RAG y faltantes, sin imprimir claves de objetos ni contenidos.

```bash
cd backend
python -m tools.diaglob_aws_privacy_audit --region us-east-2 \
  --instance diaglob-prod \
  --bucket diaglob-knowledge-765761474007-us-east-2
```

Emite hallazgos y estados no verificados de forma explícita. Las pruebas usan únicamente stubs; el script no cambia AWS. El resultado agregado no prueba por sí mismo cumplimiento de Shopify.

## 5. Pendientes de aprobación y cierre

- [x] CI del PR #274 de autorización de clientes aprobada (no implica despliegue).
- [x] Confirmación AWS: AutoSnapshot Disabled; 0 automáticas; 1 snapshot manual available.
- [x] Confirmación AWS: 0 recursos protegidos en AWS Backup; bucket AES256 y cuatro Public Access Blocks; sin lifecycle.
- [x] Código read-only para revisar recuperación/cifrado + pruebas y generador de política S3 deshabilitada.
- [ ] Autorizar costos/configuración de snapshot automático, elegir horario y activarlo en producción.
- [ ] Verificar primer snapshot automático y ejercicio de restauración en entorno aislado.
- [ ] Confirmar cifrado efectivo PostgreSQL/disk, backups coherentes, almacenamiento fuera de instancia, control de acceso y custodia de claves.
- [ ] Aprobar retención S3 por prefijo, diseñar borrado de versiones antiguas, realizar cambio controlado y verificar resultado.
- [ ] Completar cumplimiento Shopify PCD y borrado/exportación real con evidencias auditables.

**Decisión de lanzamiento:** NO-GO para afirmar protección integral PCD; los hallazgos de código y metadatos no suplen pruebas de recuperación, retención legal ni aprobación Shopify Partner.
