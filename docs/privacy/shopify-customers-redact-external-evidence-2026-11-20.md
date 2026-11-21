# DIAGLOB — Evidencia de superficies externas para `customers/redact`

> **Corte de observación: 20 de noviembre de 2026 · Lectura AWS sin mutaciones.**
> Estado global: **NO VERIFICADO / NO CERRADO**. Este informe documenta configuración y tareas pendientes, no comprueba la eliminación de un comprador ni sustituye la validación jurídica.
>
> Origen del inventario de conexiones: `docs/privacy/shopify-privacy-closure-runbook.md` (censo de producción consignado el 2026-11-20). Origen de AWS: llamadas de solo lectura a S3, Bedrock Agents y Lightsail en `us-east-2` efectuadas el mismo día. No se inspeccionaron mensajes, documentos, vectores, datos de compradores ni secretos.

## 1. Hallazgos AWS contrastados

| Superficie | Evidencia de configuración verificada | Qué sigue sin estar probado |
|---|---|---|
| S3 `diaglob-knowledge-765761474007-us-east-2` | `GetBucketVersioning=Enabled`; `GetBucketLifecycleConfiguration`: regla habilitada `privacy-noncurrent-expiry-30d`, `NoncurrentVersionExpiration.NoncurrentDays=30`, `Expiration.ExpiredObjectDeleteMarker=true` y `AbortIncompleteMultipartUpload.DaysAfterInitiation=7` | Que se hayan eliminado versiones de objetos concretos, sus réplicas o artefactos fuera del bucket; la regla no prueba supresión puntual |
| Amazon Bedrock Knowledge Bases | `ListKnowledgeBases`: **5** activas, todas `VECTOR` y con almacenamiento `S3_VECTORS` | Asociación de documentos/índices a cada comprador y su borrado verificable |
| Fuentes Bedrock | `ListDataSources` + `GetDataSource`: **4 fuentes S3** con `dataDeletionPolicy=DELETE`, todas `AVAILABLE` y con prefijos de organización/KB; **1 KB sin fuentes configuradas** | Que eliminar un documento de la fuente y sincronizar retire efectivamente todos sus vectores. `DELETE` es configuración, no constancia de ejecución |
| Vector stores | `GetKnowledgeBase`: índices en un bucket de Amazon S3 Vectors; cada KB refiere un índice propio | Evidencia por documento/vector, políticas de retención de esos índices, remanentes y uso de la KB sin fuente |
| Lightsail instancia `diaglob-prod` | `GetInstances`: auto-snapshot `Enabled`; `GetAutoSnapshots`: **7** snapshots con `Success` (14–20 nov 2026) | Prueba aislada de restauración y reconciliación de tombstones con ledger externo |
| Snapshots manuales | `GetInstanceSnapshots`: **0** snapshots manuales listados en `us-east-2` | Verificar historial/otras copias: ausencia actual no demuestra destrucción de copias antiguas fuera de esta consulta |

**Cambio respecto del runbook del repositorio:** el documento de cierre decía que faltaba lifecycle en el bucket y que persistía un snapshot manual antiguo. El estado leído el 20/11/2026 **ya no presenta esas dos condiciones en la región/cuenta consultada**. No marcar `object_storage_backups` ni `database_backups` como `verified` sin respaldar expiraciones, otras localizaciones, restores y revisiones independientes.

### Detalle mínimo de KB/DS (sin contenido de documentos)

| Knowledge Base | Fuente activa | `dataDeletionPolicy` | Tipo de vector store |
|---|---|---|---|
| `diaglob-prod-org-1-kb-13` | S3 prefijo `organizations/1/knowledge-bases/13/documents/` | `DELETE` | S3 Vectors |
| `diaglob-knowledge-main` | No se listaron fuentes | No aplica / revisar contenido residual | S3 Vectors |
| `diaglob-prod-org-1-kb-12` | S3 prefijo `organizations/1/knowledge-bases/12/documents/` | `DELETE` | S3 Vectors |
| `diaglob-prod-org-1-kb-8` | S3 prefijo `organizations/1/knowledge-bases/8/documents/` | `DELETE` | S3 Vectors |
| `diaglob-prod-org-1-kb-9` | S3 prefijo `organizations/1/knowledge-bases/9/documents/` | `DELETE` | S3 Vectors |

Documentación oficial de AWS: 
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-ds-delete.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-direct-ingestion-delete.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-data-source-sync-ingest.html

Eliminar una KB o fuente no elimina automáticamente el *recurso almacén vectorial*; investigar el ciclo de vida de sus datos. No borrar KBs compartidas ni índices globales para cumplir solicitudes de una sola tienda.

## 2. Censo de 16 procesadores: criterio de aplicabilidad

La relación siguiente **no es constancia de operaciones de borrado**. Cifras de activación provienen del censo interno en el runbook del 20/11/2026; deben reconciliarse con conexiones vivas, credenciales, logs de salida, contratos y facturación antes de atestar ausencia de uso.

| Control | Estado de inventario | Evidencia pendiente para una solicitud real |
|---|---|---|
| `shopify_admin_api` | 2 tiendas activas (censo) | Precisar originación Shopify frente a copia DIAGLOB, IDs firmados, scope y bloqueo de reimportación |
| `aws_bedrock` | 2 tiendas activas (censo) | Trazabilidad documento → tienda/comprador, eliminación/aislamiento en S3 y S3 Vectors, verificación tras sincronización |
| `google_workspace_apis` | 2 tiendas activas (censo) | Fuentes Drive/Sheets, alcance organizacional, copias indexadas y derivadas en DIAGLOB; no borrar documentos del comerciante sin instrucción |
| `email_delivery` | Sin detector concluyente | Identificar proveedor transaccional real, destinatarios, payload, retención y obligación de solicitar supresión |
| `nuvemshop_admin_api` | Sin tienda activa detectada | Confirmar ausencia de histórico de compradores Shopify compartidos |
| `dropi_supplier` | Sin tienda activa detectada | Confirmar ausencia de órdenes/contactos transmitidos y copias históricas |
| `cj_supplier` | Sin tienda activa detectada | Confirmar ausencia de órdenes/contactos transmitidos y copias históricas |
| `advertising_meta` | Sin tienda activa detectada | Revisar Pixel/CAPI, audiencias, conversiones, marketing y datos históricos |
| `whatsapp_provider` | Sin tienda activa detectada | Revisar proveedor, historial y colas salientes; suprimir contacto al comprador afectado |
| `telegram_messaging` | Sin tienda activa detectada | Revisar bots, mensajes y referencias externas |
| `instagram_messaging` | Sin tienda activa detectada | Revisar cuentas, conversaciones y referencias externas |
| `mercado_pago_payments` | Sin tienda activa detectada | Distinguir datos del comprador y registros que legalmente corresponda conservar |
| `nequi_payments` | Sin tienda activa detectada | Verificar datos y obligaciones si hubiera integración con tienda aplicable |
| `paddle_billing` | Sin tienda activa detectada | Distinguir facturación SaaS de DIAGLOB de datos de compradores Shopify |
| `files_and_object_storage` | Uso de infraestructura demostrado | Crear manifest por prefijo/objeto/versión, tipo de copia, índice derivado y borrado verificable |
| `carrier_logistics` | Sin tienda activa detectada | Inventario de transportadoras y datos de etiquetas/reclamaciones si los hubo |

**Cuidado:** el censo original resume 12 controles con cero tiendas y no asigna la misma semántica a `files_and_object_storage`. No atestar `not_in_use` para S3 solo porque no haya conexión tipo tienda: AWS demuestra que existe infraestructura activa. Tampoco confundir no detectar conexión *hoy* con nunca haber transferido información.

## 3. Superficies internas que necesitan evidencia cruzada

| Superficie | Prueba mínima exigida |
|---|---|
| SQL: perfiles, pedidos, líneas, conversaciones, checkouts | IDs de origen exactos, separación de campos compartidos y postcondiciones por `organization_id/store_id` |
| Automatizaciones y campañas | No queda envío pendiente al comprador; cancelar/drenar reintentos sin afectar a terceros |
| WhatsApp, Instagram, Telegram, email | Verificar mecanismos de contacto y entregas en tránsito, incluso si el proveedor externo no está integrado por tenant |
| Colas y workers | Replay e idempotencia; verificar tombstone **justo antes** de efectos externos |
| IA: documentos, prompts, respuestas, adjuntos, embeddings | Procedencia verificable; eliminar derivados de cliente sin destruir documentos de otras tiendas |
| S3: versiones, temporales, exports | Inventario y eliminación del objeto/versiones, retención de backups y reglas lifecycle |
| Restores: Lightsail, DB, S3, S3 Vectors | Restauración aislada con checkpoint del ledger externo **anterior** al restore; no reabrir ingreso si falla |
| Proveedores terceros | Contrato/DPA, transmisión real, solicitud de supresión, respuesta, excepción, fecha y revisor |

## 4. Registro de evidencia por `request_id` (plantilla, no completar con PII)

| Campo | Estado requerido |
|---|---|
| Recibo HMAC + tienda + identidad | Verificado con referencia opaca |
| Preview/manifest + digest | Ligado a tienda, cliente y pedidos |
| Revisión `legal_hold` + instrucción comerciante | Aprobación por caso, firmada y sin autoafirmación |
| Disposición por categoría | Retener mínimo / anonimizar / borrar, con norma y fecha si hay excepción |
| SQL & archivos/índices | Resultado, conteos, verificación y hashes de evidencia |
| Cola & recontacto | Comprobaciones de no reingesta antes de envío |
| Terceros aplicables | Acuse o evidencia de borrado; caso abierto si sigue pendiente |
| Ledger & restore | Checkpoint inmutable externo, verificación, estado de los workers |
| Revisor independiente | Persona/rol autorizado, UTC y digest del artefacto privado |
| Estado final | `fulfillment_complete=false` mientras haya incógnitas/errores |

No subir a GitHub ni a comentarios de PR los payloads de Shopify, correo, teléfono, direcciones, mensajes, valores de claves de object storage, vectores ni permisos bearer. Registrar únicamente evidencia desidentificada, digest, fecha UTC, referente privado y estado de revisión.

## 5. Próximas acciones sin borrados reales

1. **P0 jurídico:** completar la política propuesta `shopify-customers-redact-legal-approval-draft-2026-11-20.md` con responsable, comerciante y aprobación independiente; **no** emitir firmas ficticias ni afirmar `legal_hold=false` sin evidencia por caso.
2. **P0 código:** ligar `legal_hold` y `merchant_instruction` a un documento firmado *por caso* que el ejecutor valide antes de aceptar `local_redaction`. Hoy el permiso firmado expresa `legal_hold=False` sin verificar documento independiente de ese caso.
3. **P0 AWS IA:** añadir mapeo de documentos a `organization_id/store_id/customer_id` y verificar limpieza de S3 Vectors, sin borrar KB/índices compartidos.
4. **P0 proveedores:** confirmar proveedor `email_delivery`, histórico de campañas/conversaciones, y contratos/DPA; pedir confirmaciones donde existió envío real.
5. **P0 restauraciones:** ledger externo WORM, simulacro aislado y pruebas de reingesta en un dataset sintético. No usar checkpoint que provenga de la misma copia restaurada.
6. **P1 auditoría:** archivar reportes de lectura y hashes en ubicación restringida; revisión independiente y firmado de controles solo tras aceptación.

## 6. No negociables del cierre

- Ningún registro de otra tienda se borra por compartir `Customer`, email, teléfono, campaña o fuente.
- `dataDeletionPolicy=DELETE` y lifecycle S3 **no equivalen** a demostrar eliminación ejecutada.
- Responder exitosamente al webhook **no equivale** a ejecutar supresión real.
- Una atestación firmada valida autoría e integridad, **no** veracidad material sin inspección de la evidencia.
- Un `fulfilled` no se genera por pruebas sintéticas ni por el mero hecho de configurar permisos.
