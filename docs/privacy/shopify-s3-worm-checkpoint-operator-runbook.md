# DIAGLOB — Runbook técnico de checkpoint externo S3 Object Lock

**Estado:** implementación propuesta y pruebas sintéticas, **no desplegada**. Este archivo no es la declaración legal final, no acredita que exista un ledger productivo ni autoriza supresión de datos.

## Riesgo mitigado

La base de datos y su configuración de entorno pueden restaurarse a una instantánea anterior y recuperar clientes que ya fueron suprimidos. Un checkpoint HMAC calculado desde la misma instantánea no detecta esa regresión. El ledger aquí propuesto firma y protege cada checkpoint en **S3 Object Lock COMPLIANCE**, en un bucket diferente del de documentos de compradores y, preferiblemente, en una cuenta de seguridad distinta.

Fuente AWS: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html
Shopify: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance

## Operación segura

1. **Aprobación humana pendiente:** responsable jurídico y de seguridad acuerdan conservación de eventos técnicos sin PII, tratamiento de logs, backup máximo recuperable y periodo exacto de Object Lock (30–3650 días). Compliance mode no permite reducir la retención de versiones ya protegidas.
2. **Infraestructura:** revisar plantilla opcional `infra/aws/shopify-privacy-ledger-bucket.yaml` y crear **nuevo** bucket de ledger, en cuenta de seguridad independiente si está disponible; documentar región, owner, bucket arn y aprobaciones. Nunca habilitar Object Lock sobre el bucket de Knowledge ni incluir datos personales reales en el ledger.
3. **IAM:** crear rol operador **escritor** separado del rol de ejecución, privilegios mínimos de `s3:PutObject`, `s3:ListBucketVersions`, `s3:GetObject`, `s3:GetObjectRetention`, `s3:GetBucketVersioning`, `s3:GetBucketObjectLockConfiguration`. Restringir a prefijo y bucket, denegar `s3:DeleteObject` y `s3:DeleteObjectVersion`, y limitar cambios de políticas y permisos. El rol **lector** de restore no puede escribir ni borrar. La plantilla por sí sola no crea IAM/roles.
4. **Claves:** generar Ed25519 fuera de Lightsail, de DB, y de snapshots. La clave privada no se sube al servidor ni al repo. La pública se registra en configuración restringida con huella/firma de aprobación. La firma prueba integridad del evento, no la veracidad del checkpoint aportado.
5. **Origen:** `python -m tools.shopify_privacy_restore_check snapshot` sobre la DB operativa en ambiente de operador y guardar el JSON devuelto en un archivo privado. Validar el conteo, HMAC y estado de DB con revisor independiente.
6. **Firma y append:** usar CLI `tools.shopify_privacy_s3_ledger` desde la estación autorizada con el archivo de checkpoint. Verificar el bucket, historial completo de versiones y firmar un nuevo registro inmutable con modo COMPLIANCE explícito, checksum y AES256. El CLI verifica la lectura de vuelta; no asume que un PUT equivale a custodia.
7. **Restore:** antes de iniciar webhook importers, campañas, workers y tareas en un restore aislado, ejecutar `verify-restore` contra S3, verificar la firma de todos los eventos, versiones, retención, ausencia de delete-markers/reescrituras, cadena, último HMAC y mínimo de tombstones. Si falla, **no reanudar ingesta ni recontacto**.
8. **Concurrencia:** solo un escritor activo bajo bloqueo organizativo. Si dos escritores crean el mismo índice de secuencia, el verificador detecta una bifurcación y exige intervención; S3 Object Lock no resuelve transacciones distribuidas. Nunca cambiar manualmente el objeto para «arreglar» el error.
9. **Vencimientos:** la retención aprobada debe superar la máxima edad de todos los backups restaurables, incluyendo snapshots y replicaciones. El protocolo actual exige comprobar **cada** evento retenido; si expira un evento antiguo antes de migrar/renovar la cadena, la verificación se bloquea. Planificar rollover firmado antes de vencer, con evidencia de auditoría independiente.
10. **Separación de funciones:** el operador que firma checkpoint no sustituye al revisor jurídico. El permiso `local_redaction` y los controles del comercio son requisitos adicionales.

### Ejemplos sin credenciales

```bash
cd backend
python -m tools.shopify_privacy_s3_ledger keygen --out /private/diaglob/worm-ledger-signer.pem

# Obtener snapshot por una vía segura antes de este paso:
python -m tools.shopify_privacy_restore_check snapshot > /private/evidence/latest-checkpoint.json

# Auditar el ledger existente (usar la clave pública mostrada al generar clave):
python -m tools.shopify_privacy_s3_ledger verify \
  --bucket <bucket-worm-aprobado> --prefix privacy/restore/checkpoints \
  --public-key <clave-publica-ed25519-b64url>

python -m tools.shopify_privacy_s3_ledger append \
  --bucket <bucket-worm-aprobado> --prefix privacy/restore/checkpoints \
  --public-key <clave-publica-ed25519-b64url> \
  --private-key /private/diaglob/worm-ledger-signer.pem \
  --checkpoint /private/evidence/latest-checkpoint.json \
  --request-id <request-id-opaco-64hex> --retention-days <dias-aprobados>

# Solo en un restore aislado, con base a validar y rol lector:
python -m tools.shopify_privacy_s3_ledger verify-restore \
  --bucket <bucket-worm-aprobado> --prefix privacy/restore/checkpoints \
  --public-key <clave-publica-ed25519-b64url>
```

La salida no contiene secretos ni selectors. El CLI **no** escribe `SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC` en producción; esa distribución requiere procedimiento seguro independiente, validación de origen y activación del motor.

## Compatibilidad y límites

- La implementación no ejecuta `CreateBucket`, `DeleteObject`, `PutBucketObjectLockConfiguration`, supresión de datos ni cambios a las variables de producción.
- El bucket de Knowledge observado el 20/11/2026 no tiene Object Lock. **No** es un ledger válido.
- No se ha comprobado que los snapshots automáticos de Lightsail puedan reconciliarse con un ledger de este tipo: falta prueba de restauración aislada.
- `verify_worm_ledger` valida toda la cadena actual de versiones y firmas; la garantía de retención depende además de IAM, control de cuenta y del periodo aprobado.
- Las pruebas simuladas no reemplazan una prueba AWS contra un bucket WORM real.
- Ninguna operación establece `fulfillment_complete=true`. Esto es una barrera contra regresión de supresiones, no una prueba de eliminación en proveedores.

## Prueba

```bash
cd backend
pytest -q tests/test_shopify_privacy_worm_ledger.py
```
