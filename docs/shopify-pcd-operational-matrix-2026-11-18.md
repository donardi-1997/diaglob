# DIAGLOB — Matriz operativa PCD Nivel 2

**Fecha de corte:** 2026-11-18  
**Estado:** NO-GO para atestación pública  
**Aplicación:** Shopify App ID `416524435457`  
**Alcance:** evidencia disponible en código, pruebas y metadatos AWS. No es una certificación independiente.

## Regla de decisión

`Sí` solo significa que existe evidencia operativa suficiente para la afirmación
concreta. La existencia de código, un documento o cifrado parcial no se
interpreta como cumplimiento integral. `No` significa que la evidencia actual
no permite responder afirmativamente; no implica necesariamente que el control
no exista. `No corresponde` solo se usará con una justificación explícita.

## Evidencia AWS read-only

Auditoría ejecutada el 2026-11-18 en `us-east-2` mediante las operaciones
metadata-only `GetInstance`, `GetAutoSnapshots`, `GetInstanceSnapshots`,
`GetBucketVersioning`, `GetBucketLifecycleConfiguration`, `GetBucketEncryption`,
`GetPublicAccessBlock`, `GetBucketLogging`, `ListObjectsV2`,
`ListObjectVersions` y `ListProtectedResources`.

| Control observado | Resultado verificable | Estado PCD | Limitación |
|---|---|---:|---|
| Snapshot automático de Lightsail | Add-on `AutoSnapshot` habilitado a las 07:00 UTC; 7 snapshots con estado `Success` del 12 al 18 de noviembre | Sí, como punto de recuperación de instancia | No prueba backup consistente de PostgreSQL, cifrado, retención legal ni restore |
| Snapshot manual Lightsail | 1 snapshot disponible, creado el 2026-10-15 | Sí, como metadato de existencia | No se ejecutó ni evidenció restauración aislada |
| Versionado S3 | `Enabled` | Sí, como control de historial | Versionado no equivale a política de retención o borrado conforme a finalidad |
| Cifrado por defecto S3 | `AES256` | Sí, solo para ese bucket | No acredita cifrado de PostgreSQL, disco, snapshots ni otros proveedores |
| Bloqueo de acceso público S3 | Las cuatro opciones están `true` | Sí, para ese bucket | No sustituye revisión de IAM ni prueba de acceso efectivo |
| Lifecycle S3 | `NoSuchLifecycleConfiguration` | No | No hay expiración verificable de versiones no actuales |
| S3 server access logging | Configuración vacía | No | No existe evidencia de access logging del bucket |
| AWS Backup | 0 recursos protegidos | No | No hay protección AWS Backup acreditada para la base/instancia |

La auditoría no leyó objetos, filas de base de datos, logs privados, secretos ni
contenido vectorial, y no realizó modificaciones.

## Matriz de declaraciones

| Declaración / control | Estado | Evidencia y condición para cerrar |
|---|---:|---|
| Minimización y finalidad | No | Inventario técnico parcial; falta aprobación del catálogo de campos, finalidades, derivados y procesadores |
| Información al comerciante, política y acuerdo de datos | No | Deben verificarse URLs públicas, versión vigente y acuerdos aplicables |
| Consentimiento, opt-out y perfilamiento | No | Automatizaciones y comunicaciones requieren revisión de base legal, exclusiones y decisiones significativas |
| Retención y borrado | No | No existe política operativa aprobada ni lifecycle S3; exportación/borrado E2E no verificados |
| Cifrado en tránsito y reposo | No | HTTPS, Fernet para credenciales Shopify y SSE-S3 parcial; falta cobertura de DB, disco, backups y proveedores |
| Backups cifrados | No | Hay snapshots automáticos exitosos, pero no evidencia de cifrado de backup, custodia de claves, consistencia ni restauración |
| Separación test/producción | No | La prueba Shopify usó backend de producción; falta entorno aislado y prueba de ausencia de PII productiva |
| DLP y acceso staff | No | Hay autorización por organización/tienda y pruebas sintéticas; falta inventario de salidas/proveedores y pruebas DLP E2E |
| Contraseñas y cuentas staff | No | Login y recuperación E2E fueron probados, pero falta evidencia de política, MFA/staff access y administración completa |
| Logging de acceso PCD | No | Existe evento `CUSTOMER_PCD_READ`; falta almacenamiento centralizado, cobertura, retención, revisión y alertas |
| Respuesta a incidentes | No | `docs/security/incident-response-plan.md` sigue en draft; faltan responsables nombrados, aprobación y tabletop con acciones |
| Webhooks de privacidad Shopify | No | HMAC/inbox/fixtures existen; fulfillment, exportación y borrado reales no están verificados de extremo a extremo |

## Evidencia de código y pruebas que sí puede adjuntarse

- `backend/app/api/customers.py`: autorización por organización/tienda y
  eventos de lectura PCD sin incluir valores identificatorios.
- `backend/app/services/shopify_webhook_service.py`: fuentes de nombre,
  dirección, email y teléfono recibidas desde eventos autorizados de Shopify.
- `backend/tests/test_shopify_pcd_customer_store_isolation.py`: pruebas de
  aislamiento sintético.
- Suite backend registrada el 2026-11-18: `3084 passed`; esto acredita regresión
  de software, no controles operativos de infraestructura.

## Bloqueadores antes de responder “Yes/Compliant”

1. Definir y aprobar retención por categoría, incluyendo versiones S3, backups,
   exportación, borrado y legal holds.
2. Establecer backups cifrados independientes, retención, control de claves y
   ejecutar un restore aislado con datos sintéticos; registrar resultado y RTO.
3. Separar test y producción, con credenciales y datos sintéticos independientes.
4. Centralizar logs PCD con control de acceso, retención y revisión demostrable.
5. Completar inventario DLP/proveedores y probar que no se filtran PCD a logs,
   tickets, CI o herramientas externas.
6. Nombrar responsables de incidentes, aprobar el plan y ejecutar el tabletop
   sintético descrito en `docs/security/incident-response-plan.md`.

**Conclusión:** el expediente permanece **NO-GO**. Los snapshots automáticos
exitosos mejoran la disponibilidad de recuperación, pero no permiten cambiar
las respuestas de backups cifrados, retención, separación, logging o incident
response a “Sí”.
