# DIAGLOB — activación controlada del motor de privacidad Shopify

**Estado:** especificación técnica pendiente de aprobación jurídica y de simulacro de restore.
**Efecto del parche:** el script de habilitación se niega a activar el procesamiento si faltan las condiciones de custodia. No genera ni rota claves de supresión, no autopublica aprobación de política y no crea checkpoints.

## Brecha corregida

`scripts/enable-shopify-privacy-processing.sh` antes:
- escribía `SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256` calculado desde el repositorio como si fuese aprobación;
- generaba una nueva clave de supresión si no existía, potencialmente imposible de reconciliar con un checkpoint previamente almacenado;
- podía activar `SHOPIFY_PRIVACY_PROCESSING_ENABLED=true` sin checkpoint independiente ni clave de revisión legal, aunque las rutas de reingesta ahora fallan cerradas cuando falta checkpoint.

El nuevo preflight **antes de modificar el archivo de entorno** exige:

1. Digest externo de política aprobado en `SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256`, igual al documento técnico desplegado. **Un valor de hash por sí solo no es prueba legal**; adjuntar aprobación auténtica en bóveda restringida.
2. Clave pública Ed25519 de revisión jurídica `SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY` válida y distinta de las claves de ejecución y atestación.
3. Clave `SHOPIFY_PRIVACY_SUPPRESSION_KEY` preexistente, custodiada y recuperable, con mínimo 32 bytes. **Nunca regenerarla en producción** sobre tombstones existentes.
4. `SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC` de 64 caracteres hexadecimales y `SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS` entero no negativo.
5. Verificación **externa e independiente** de que el checkpoint proviene de un ledger append-only no restaurado y coincide con la base actual. El script solo verifica formato/presencia; la **proveniencia e integridad del ledger deben validarse fuera del script**.
6. Dos claves públicas proporcionadas al script de activación para atestación y ejecución, diferentes de la clave de revisor legal.

Si falla alguna condición, el script termina antes de editar su archivo de entorno o reiniciar servicios. Es **un cambio de seguridad que requiere coordinación**, no una orden para ejecutarlo automáticamente.

## Checklist previo del operador

- Responsable jurídico y comerciante: política aprobada, excepciones, poderes de firmantes, instrucción por caso.
- Seguridad: custodiar claves privadas **fuera del servidor**; claves públicas legales, atestación y ejecución con identidades separadas; rotación documentada.
- Infraestructura: ledger **fuera** de Lightsail y de sus backups, preferiblemente bajo cuenta/protección independiente; WORM/Object Lock verificado, sin efectos sobre datos de compradores.
- Restore: capturar el checkpoint desde el ledger, ejecutar `python -m tools.shopify_privacy_restore_check verify --expected-hmac <HMAC> --minimum-records <N>` contra el entorno controlado antes de reabrir la ingesta. **No tomar el HMAC de la base restaurada.**
- CI/staging: ejecutar tests de HMAC, multisede, no-data, export, redact, shop-redact, SSL, replays y permisos.
- Operación: respaldar env sin enviarlo a tickets; aprobar ventana de despliegue y plan de rollback, verificar Health y API.

## Evidencia AWS de solo lectura, 20/11/2026

En la cuenta/región inspeccionada:
- Bucket `diaglob-knowledge-765761474007-us-east-2` versionado, con expiración de versiones no actuales a 30 días y multipart a 7 días.
- `GetObjectLockConfiguration` devolvió `ObjectLockConfigurationNotFoundError` para ese bucket: **el bucket Knowledge no está configurado como ledger WORM**.
- `ListBuckets` detectó un solo bucket cuyo nombre contiene `diaglob`. Esto **no prueba** que no exista un ledger seguro en otra cuenta o servicio; su ubicación/integridad debe evidenciarse.
- Lightsail `diaglob-prod`: 7 snapshots automáticos exitosos, 0 manuales listados, sin prueba aislada de restauración.
- Bedrock: 5 KB activas con S3 Vectors; cuatro fuentes S3 con `dataDeletionPolicy=DELETE`, una KB sin fuentes. No es evidencia de borrado de vectores de un comprador.

No se efectuaron mutaciones AWS.

## Cierre exigible

**No fusionar ni desplegar** este cambio como autorización de borrado. Fusionarlo solo tras revisar su compatibilidad y comprobar en staging el preflight fail-closed. El estado global de DIAGLOB debe seguir en "no certificado" hasta que cada uno de los diez controles por caso tenga evidencia independently reviewed y un proceso de cierre verificable.
