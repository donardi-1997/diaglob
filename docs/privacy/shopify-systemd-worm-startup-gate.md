# DIAGLOB — barrera de restauración WORM al iniciar servicios

> **NO DESPLEGADO / NO APROBADO.** El presente es un procedimiento técnico de seguridad, no la declaración legal final. Las plantillas drop-in no se instalan automáticamente por Git ni prueban que el ledger productivo exista.

## Brecha que cubre

El chequeo del script de habilitación controla el momento de activación manual, **pero un restart automático de systemd podía arrancar la API o worker sin consultar el ledger independiente**. Tras un restore de snapshot podría recuperarse también una copia antigua de `/etc/diaglob/diaglob.env`; aunque DB y HMAC de ese archivo coincidieran entre sí, ambos podrían estar atrasados frente al registro WORM fuera de Lightsail.

Se añade el comando read-only:
`python -m tools.shopify_privacy_startup_guard`.

Requiere la existencia de los siguientes valores en la EnvironmentFile de los servicios, protegida por permisos y respaldos independientes:
- `SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET`
- `SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX`
- `SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY`
- `SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC`
- `SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS`
- `SHOPIFY_PRIVACY_SUPPRESSION_KEY`

Verifica el ledger desde AWS mediante Object Lock, versiones, firmas Ed25519, secuencia, retención vigente, último HMAC y digest de política; luego compara el checkpoint externo con la base restaurada. Si falla, sale con código 1, sin imprimir secretos ni PII. **No hay ruta para ignorar el chequeo porque la base tenga cero tombstones o porque `SHOPIFY_PRIVACY_PROCESSING_ENABLED=false`.**

## Instalación después de aprobación

Los drop-ins versionados pero **no instalados** se encuentran en:
- `backend/ops/privacy-gate-dropins/diaglob-api.service.d/20-shopify-privacy-worm.conf`
- `backend/ops/privacy-gate-dropins/diaglob-automation-worker.service.d/20-shopify-privacy-worm.conf`

Solo después de crear bucket WORM real, probar su clave de lectura, aprobación legal, backup aislado y ventana operativa, un operador con permisos sudo copia los archivos a:

```
/etc/systemd/system/diaglob-api.service.d/20-shopify-privacy-worm.conf
/etc/systemd/system/diaglob-automation-worker.service.d/20-shopify-privacy-worm.conf
```

Después ejecuta `systemctl daemon-reload` y valida con `systemctl cat`, `systemd-analyze verify` y pruebas de arranque en staging **antes** de activar los servicios productivos. En ausencia de AWS, clave válida o checkpoint, los servicios protegidos **no deben iniciar**. Planificar operativamente esa pérdida de disponibilidad deliberada.

La cuenta/principal AWS que ejecuta ExecStartPre debe tener **solo lectura** del bucket WORM. Nunca recibe clave privada de firma, ni s3:PutObject, ni permisos para cambiar retención o política del bucket.

## Pruebas obligatorias antes de producción

1. Inicio normal contra última ancla WORM válida, estado de API/worker `active`.
2. Snapshot antiguo con cero tombstones y entorno antiguo: arranque denegado.
3. Simular S3/AWS temporalmente inaccesible, firma errónea o versión borrada: arranque denegado.
4. Cambio de política o último checkpoint sin revalidación: arranque denegado.
5. Restablecer backup compatible desde ledger externo y comprobar prevención de reingreso/recontacto.
6. Ensayar rollback de desplegar drop-ins, aprobación de la ventana y evidencia de seguridad.
7. Evaluar rendimiento de lectura de toda la cadena WORM por arranque; ajustar paginación, permisos y retención.

El flujo de AWS real no está implementado. Ninguna eliminación de compradores o archivos de proveedores se hace desde este comando, y `fulfillment_complete` continúa falso.

```bash
cd backend
pytest -q tests/test_shopify_privacy_startup_guard.py tests/test_shopify_privacy_worm_ledger.py
```
