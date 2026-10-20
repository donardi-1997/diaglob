# DIAGLOB — Seguridad PCD: controles verificados y pendientes (2026-10-20)

**Alcance**: auditoría parcial de código GitHub y metadatos AWS en `us-east-2`. No incluye lectura de datos personales, secretos, contenido de objetos, sistema de archivos de Lightsail ni permisos de Shopify Partner. No es certificación independiente ni prueba de protección de todas las tablas.

## Hallazgo P0: control de acceso a clientes

`backend/app/api/customers.py` comprobaba permisos de rol y organización, pero sus rutas no exigían siempre pertenencia a la tienda:
- Las rutas por tienda `/api/stores/{store_id}/customers/classifications` y `.../audience` aceptaban tiendas de la misma organización aunque la membresía no tuviera acceso a ellas.
- `/api/customers`, `/api/customers/summary` y `/api/customers/{id}` aceptaban `store_id` omitido, pudiendo consultar toda la organización para personal con acceso limitado a una o varias tiendas.
- Medida: ahora se verifica `membership.stores`/ `all_stores`; si hay **una** tienda asignada activa se fuerza ese scope, si hay varias y no se especifica tienda se deniega el acceso de forma segura (403); propietarios/miembros con `all_stores` conservan la vista org-wide. Las rutas con `store_id` exigen tienda activa asignada.
- Se agregan eventos de auditoría `CUSTOMER_PCD_READ` sin PII, con tipo de operación, ID de usuario, organización y tienda. **No** se verificó destino centralizado ni retención de esos logs.
- Alcance limitado a estas rutas: no prueba que todas las rutas de pedidos, mensajes, datos enriquecidos o automatizaciones compartan la misma política. El modelo `Customer` sigue compartido a nivel organización; los campos de identidad comunes de un cliente de dos tiendas requieren revisión adicional de minimización/separación.

## AWS: verificación read-only del entorno identificado

| Superficie | Evidencia observada | Evaluación |
| --- | --- | --- |
| S3 `diaglob-knowledge-765761474007-us-east-2` | `GetBucketEncryption` devuelve SSE-`AES256` por defecto | Cifrado por defecto **verificado** para ese bucket, no para toda la infraestructura |
| El mismo bucket | `GetPublicAccessBlock`: cuatro bloqueos en `true` | Bloqueo de acceso público verificado |
| El mismo bucket | `GetBucketVersioning`: Enabled | Versiones anteriores pueden retener datos personales |
| El mismo bucket | `GetBucketLifecycleConfiguration`: `NoSuchLifecycleConfiguration` | **Brecha abierta:** no hay reglas lifecycle ni expiración de versiones antiguas |
| El mismo bucket | `GetBucketPolicyStatus`: `NoSuchBucketPolicy` | Sin política de bucket configurada; no implica por sí solo exposición pública |
| Lightsail `diaglob-prod` | Instancia Ubuntu activa, 60 GiB system disk; `GetDisks` sin discos adicionales | No se verificó cifrado efectivo del disco/volumen ni datos de PostgreSQL |
| Lightsail snapshots | Un snapshot de instancia `diaglob-prod-pre-release-20261015`, ningún snapshot de disco adicional en resultado | Copia puntual **no prueba** cron/retención/restauración automáticos |
| RDS `us-east-2` | `DescribeDBInstances` sin instancias | No demuestra cifrado de la BD que corre en Lightsail ni excluye otros entornos |

La información se obtuvo mediante metadatos de AWS sin mutaciones. Es imprescindible no interpretar un bucket cifrado como prueba del cifrado de `customers`, `orders`, `conversations`, proveedores o backups de servidor.

## Registro de declaraciones Shopify Partner

**No accedimos ni cambiamos** `Apps → API access requests → Protected customer data access` ni `Data protection details` en Partner. Reconciliar antes de enviar una solicitud:

| Categoría/campo | Origen comprobado en código | Motivo funcional propuesto | Decisión |
| --- | --- | --- | --- |
| Nivel 1: pedido/cliente | Webhooks pedidos y órdenes | Vínculo operativo, seguimiento, fulfillment | Solicitar solo si se mantiene flujo |
| Nombre | `shopify_webhook_service._upsert_customer` | Reconocer destinatario y entrega | Justificar/solicitar |
| Email | Webhook cliente/pedido | Vinculación/contacto | Justificar/solicitar |
| Teléfono | Webhook cliente/pedido/dirección | Contacto/entrega | Justificar/solicitar |
| Dirección | `Order.shipping_address` | Entrega | Justificar/solicitar |

**No marcar «No necesita acceso a datos protegidos»** sin eliminar de verdad esos tratamientos. Los nombres de campos y opciones exactas del formulario deben confirmarse en el Partner Dashboard vigente.

## Puertas de cierre

- [x] Token Shopify cifrado con Fernet en aplicación (código revisado; no valida custodio de la clave).
- [x] Bloqueo por asignación de tienda propuesto en rutas de clientes y auditoría de lectura sin PII.
- [x] Metadatos AWS de cifrado/bloqueo público/versioning y existencia de snapshot registrados.
- [ ] CI y pruebas de roles, organización, tiendas y perfiles compartidos en todas las rutas sensibles.
- [ ] Cifrado de DB/disk/backup y claves: examen de la configuración real, cifrado de backups y simulacro de restore.
- [ ] Definir expiración de versiones S3 y retención legal; aplicar lifecycle tras análisis de impacto en datos y restauración, no automáticamente.
- [ ] Retención/acceso de logs y alertas, MFA, IAM, permisos internos de operadores y proveedores.
- [ ] Inventario de todos los procesadores y flujos PCD externos; borrar/exportar datos reales según obligaciones antes del cierre.
- [ ] Capturas saneadas de Partner y estado PCD nivel 1/2 aprobado en aplicación/tienda reales.
- [ ] QA end-to-end y aprobación de seguridad/privacidad antes de publicación Shopify.

**Estado global: NO-GO** para atestiguar controles PCD Shopify. La protección a nivel de código y el cifrado de un bucket son avances parciales, no una demostración de cumplimiento de extremo a extremo.

Documentación oficial: https://shopify.dev/docs/apps/launch/protected-customer-data
