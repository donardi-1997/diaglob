# Shopify GDPR — verificación del ledger S3 WORM antes de habilitar privacidad

> **Implementación en PR, no ejecutada en producción.** El estado de cumplimiento sigue abierto hasta configurar un bucket externo con Object Lock, credenciales y un simulacro real de restauración.

La habilitación con `scripts/enable-shopify-privacy-processing.sh` comprueba ahora:

1. Aprobación de política, clave de supresión estable, revisor legal y permiso técnico separados.
2. Bucket, prefijo y clave pública independiente del firmante de ledger en `/etc/diaglob/diaglob.env`: `SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET`, `SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX`, `SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY`.
3. Lectura directa de S3 Object Lock, versionado, todas las versiones, firmas Ed25519, cadena completa, retenciones aún vigentes, ausencia de delete markers y reescrituras.
4. Igualdad estricta entre último HMAC/minimum/política del ledger y las variables de activación **antes de editar el archivo de entorno**.
5. Comprobación de tombstones de la base de datos real contra **el HMAC traído del ledger**, no contra un hash recién calculado desde la base restaurada.

Un error detiene el script con `PRIVACY_WORM_LEDGER_PREFLIGHT_FAILED`, sin mostrar secretos. Si falla el preflight sin haberse editado el archivo, no se reinician servicios con el entorno antiguo; si se modificó el archivo, se restaura la copia con permisos restringidos.

## Advertencia P0: falta el gate de arranque de cada servicio

Esta protección funciona al **invocar manualmente el script de habilitación**. **No garantiza por sí sola** que los workers/ingesta que arrancan por systemd tras un restore o un reboot hayan validado S3 previamente. Antes de certificar protección integral se requiere desplegar un `ExecStartPre` o control equivalente independiente de respaldos para `diaglob-api` y `diaglob-automation-worker`, probado en staging con AWS temporalmente inaccesible y con una base antigua. Si falla, el sistema debe impedir la reingesta y el recontacto, no limitarse a mostrar un error.

La firma del ledger no reemplaza aprobaciones legales por caso ni las verificaciones de borrado de proveedores externos.

## No realizado

- No se ha creado bucket WORM ni asignado IAM read/write.
- No se ha ejecutado este script en Lightsail.
- No se ha aprobado el plazo de conservación del ledger.
- No se ha probado restauración real en ambiente aislado.
- No se han marcado casos Shopify como cumplidos.

## Pruebas sintéticas

```bash
cd backend
pytest -q tests/test_shopify_privacy_activation_preflight.py tests/test_shopify_privacy_worm_ledger.py
```
