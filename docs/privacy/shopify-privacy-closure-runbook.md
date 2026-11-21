# Cierre del issue #266 — atestaciones firmadas de privacidad Shopify

El auditor `app.shopify_privacy_operational_audit` ya no tiene bloqueos fijos.
Cada bloqueo se libera solo con **atestaciones firmadas** (Ed25519, clave privada
fuera del servidor) que estén vigentes, ligadas al digest exacto de
`config/shopify-privacy-policy.json` y no contradichas por datos vivos.

| Bloqueo | Se libera cuando |
|---|---|
| `SHOPIFY_ACTIVE_VERSION_SUBSCRIPTIONS_NOT_VERIFIED_BY_THIS_AUDIT` | `shopify_compliance_subscriptions = verified` |
| `REAL_SHOPIFY_DELIVERY_NOT_VERIFIED_BY_THIS_AUDIT` | lo anterior + ≥1 recibo con HMAC verificado (hoy: 9) |
| `LEGAL_RETENTION_AND_HOLDS_NOT_APPROVED` | 6 categorías de retención + `legal_holds` = `approved` |
| `EXTERNAL_PROCESSOR_ERASURE_NOT_VERIFIED` | 16 procesadores atestados (`erasure_verified`, `not_in_use` o `no_personal_data_retained`) |
| `BACKUP_RESTORE_AND_REINGESTION_NOT_VERIFIED` | 6 controles de backup/restore = `verified` |
| `LIVE_CUSTOMER_EXPORT_NOT_ENABLED` | `SHOPIFY_PRIVACY_PROCESSING_ENABLED=true`, digest exacto aprobado, claves Ed25519 técnica/legal válidas y distintas, y `SHOPIFY_PRIVACY_DELIVERY_KEY` Fernet válida |
| `LIVE_CUSTOMER_AND_SHOP_REDACTION_NOT_ENABLED` | processing/digest y claves Ed25519 anteriores + `SHOPIFY_PRIVACY_SUPPRESSION_KEY` de al menos 32 bytes + checkpoint HMAC y conteo externo con formato válido |

Una atestación `not_in_use` se invalida automáticamente si cualquier tienda
activa ese procesador. Las atestaciones caducan (máx. 400 días).

## Procedimiento (estación del operador)

```powershell
cd backend
# 1. Una sola vez; guardar la clave privada en el gestor de contraseñas.
.venv\Scripts\python -m tools.shopify_privacy_attestation keygen --out $HOME\.diaglob-privacy
# 2. Por control: la evidencia se queda privada, solo su SHA-256 entra en Git.
.venv\Scripts\python -m tools.shopify_privacy_attestation sign --key $HOME\.diaglob-privacy\attestation.key `
  --control legal_holds --determination approved --evidence C:\privado\aprobacion-retencion.pdf `
  --attestor-role privacy_owner
# 3. Ver estado.
.venv\Scripts\python -m tools.shopify_privacy_attestation status --public-key <clave pública>
```

Las atestaciones en `config/privacy-attestations/` se fusionan por PR. Al
cambiar la política, todas deben volver a firmarse.

## Estado histórico verificado en producción (2026-11-20, solo lectura, sin PII)

> Esta sección es una captura histórica, no el estado contractual actual. Fue
> superada por la auditoría de 2026-11-21 (30/30 atestaciones válidas). Consultar
> siempre `app.shopify_privacy_operational_audit` en el commit desplegado.

- 7 tiendas. Procesadores activos: `shopify_admin_api` (2), `aws_bedrock` (2),
  `google_workspace_apis` (2). `email_delivery` sin detector: requiere confirmación manual.
  Los otros 12 procesadores: 0 tiendas.
- Lightsail: snapshots automáticos diarios, 7 retenidos.
- **Hallazgo histórico:** snapshot manual `diaglob-prod-pre-release-20261015`
  excedía el objetivo técnico actual de 30 días.
- **Pendiente:** bucket `diaglob-knowledge-765761474007-us-east-2` versionado sin
  regla de ciclo de vida: versiones antiguas se conservan indefinidamente.
- En esa fecha histórica, las variables de ejecución estaban sin configurar.

## Evidencia requerida por control

**Shopify**
- `shopify_compliance_subscriptions`: captura/exportación de la versión
  **publicada** de la app en Partner Dashboard mostrando las tres URLs de
  cumplimiento (`customers/data_request`, `customers/redact`, `shop/redact`).

**Retención** (`approved`): documento de aprobación con plazo, base legal y
responsable por categoría: `customer_contact`, `financial_orders`,
`shipping_and_returns`, `conversations`, `automations_and_ai`,
`logs_and_audit`, y regla de bloqueo legal `legal_holds`.

**Procesadores**
- `shopify_admin_api`: Shopify es el controlador de origen; evidencia de que
  la redacción local elimina copias y que no se reescribe en Shopify.
- `aws_bedrock`: DPA de AWS + evidencia de que no se retienen prompts y de
  borrado de las bases de conocimiento afectadas (S3/vectores).
- `google_workspace_apis`: solo lectura de archivos del comerciante;
  evidencia de borrado de las copias indexadas al eliminar la fuente.
- `email_delivery`: confirmar proveedor real y su retención.
- Los 12 sin uso: `not_in_use` con el censo como evidencia.

**Backup/restore** (`verified`)
- `database_backups`: caducidad de snapshots ≤ objetivo de la política.
- `object_storage_backups`: regla de ciclo de vida para versiones no actuales.
- `restore_reconciliation` y `tombstone_offsite_ledger`: simulacro de
  restauración con `tools.shopify_privacy_restore_check` usando un checkpoint
  guardado fuera de la base.
- `async_automation_queues`, `provider_replay`: evidencia de que las colas
  comprueban supresiones antes de reenviar.

## Cierre

1. Todas las atestaciones válidas y variables configuradas.
2. `privacy_fulfillment_release_ready: true` en el despliegue de producción.
3. La siguiente solicitud real se ejecuta con permiso firmado por caso.
4. Cerrar #266 con el enlace a la ejecución del auditor.
