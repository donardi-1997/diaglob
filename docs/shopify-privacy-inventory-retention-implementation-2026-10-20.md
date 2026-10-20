# DIAGLOB — Inventario por campos y revisión de conservación (2026-10-20)

**Estado: IMPLEMENTACIÓN DE REVISIÓN, NO APROBACIÓN LEGAL NI TRATAMIENTO REAL.**

Este módulo amplía el inventario previo de tablas de Shopify con una clasificación conservadora **de campos** obtenidos exclusivamente de `Base.metadata` (SQLAlchemy). No hace lecturas de filas ni conexiones a bases de datos. No activa exportación, borrado, tombstones ni entrega de datos reales.

## Endpoints internos (requieren `X-Internal-Secret`)

- `GET /api/internal/shopify/privacy/inventory`
- `GET /api/internal/shopify/privacy/retention/template`

**Seguridad:** el valor `DIAGLOB_INTERNAL_SECRET` debe existir y coincidir; de lo contrario, responde 401. No introducir secretos en URL ni adjuntarlos en informes. Este inventario es interno y no debe usarse como anuncio público de cumplimiento.

## Cómo usar el inventario

1. Ejecutar lectura autenticada en entorno de revisión sin imprimir tokens/encabezados en logs.
2. Guardar la huella `schema_sha256` por commit/despliegue para identificar cambios de esquema; **no** es un hash de datos de compradores.
3. Revisar `field_reviews`: `table`, `column`, `category`, `coverage`, `subject_linkage` y `retention_review`. La detección identifica categorías candidatas (contactos, credenciales, direcciones, identificadores, comunicaciones, JSON, bytes y texto libre). No confirma dónde hay PII ni a quién pertenece.
4. Priorizar `unclassified_sensitive_tables` y `coverage=unclassified`; una tabla JSON de nombre genérico también se marca.
5. Resolver `subject_linkage` con una ruta probada de `organization_id`, `store_id`, `shop_id` y un sujeto firmado, incluyendo FKs, tablas compartidas, filas huérfanas y registros derivados. La existencia de las columnas **no verifica** aislamiento multitienda.
6. Revisar campos no detectados por heurísticas y las `external_sources` (proveedores, prompts externos, archivos, colas, logs, backups). Ninguna heurística garantiza cobertura total.

**Criterios de aceptación futuros:** propietario y finalidad de cada fuente, trazabilidad campo/sujeto/tienda, clasificación humana, ruta de exportación completa, acción de anonimización/supresión, respaldos y terceros, evidencias de pruebas. Debe conservarse una huella de versión del esquema y reabrirse el inventario al detectar nuevas columnas.

## Cómo usar la plantilla de conservación

`retention/template` devuelve las mismas seis categorías operativas de `RETENTION_CONTROLS`:
`customer_contact`, `financial_orders`, `shipping_and_returns`, `conversations`, `automations_and_ai`, `logs_and_audit`.

Para cada categoría el revisor debe documentar:

- finalidad, base jurídica y jurisdicción;
- duración exacta y su evento de inicio;
- obligaciones legales, excepciones y legal holds;
- datos mínimos y mecanismo de borrado/anonimización;
- subprocesadores y copias;
- expiración de backups y conciliación posterior a restauración;
- aprobación independiente y evidencia verificable.

**No existe un período predefinido.** `retention_duration: null`, `independently_approved: false`, `policy_approved: false` y `live_erasure_authorized: false` son deliberados. La plantilla **no es** un formulario para autoaprobar la ejecución. La aprobación real requerirá un flujo de control independiente, jurídico/financiero/seguridad, con evidencia vinculada y controles implementados en los procesadores.

## Pruebas automáticas

```bash
cd backend
pytest -q tests/test_shopify_privacy_inventory_report.py tests/test_shopify_privacy_inventory_coverage.py
```

Comprueban: detección JSON/texto/contacto/credenciales, tablas sin PII evidente, cambios de huella tras DDL, ausencia de aprobación automática, rechazo de secretos ausentes o erróneos, cobertura de datos compartidos y template sin plazos.

## Pendientes deliberados

- Verificar tablas físicas de la BD productiva y fuentes fuera del ORM.
- Revisar verdaderas rutas de aislamiento, contenido no estructurado y datos derivados en proveedores.
- Acordar períodos y obligaciones según país/contrato y aprobar formalmente.
- Comprobar Shopify Dev Dashboard/version activa y webhooks válidos reales.
- Construir ejecución de exportación y supresión con pruebas E2E y conciliación de backups.

**No desplegar como función que declare cumplimiento.** Este cambio proporciona el diagnóstico operativo para diseñar los pasos posteriores sin autorizar mutaciones sobre clientes o tiendas.
