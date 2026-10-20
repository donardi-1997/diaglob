# DIAGLOB — Hito de reconciliación de fuentes de exportación Shopify

**Estado: preflight de cobertura y procedencia por solicitud, sin lectura de contenido personal.**
No realiza exportación ni autoriza una entrega. Construido sobre PR #277, ya integrado en `main`.

## Qué se implementa

`GET /api/internal/shopify/privacy/cases/{request_id}/export/provenance`

- Requiere `X-Internal-Secret` y evidencia `received` de webhook firmado; valida asociación exacta de solicitud, cliente Shopify y tienda.
- Reutiliza el inspector de conteos existente: **6 fuentes locales** (perfiles, pedidos, artículos, conversaciones, mensajes y checkouts) y **5 fuentes de automatización** vinculadas por tienda y sujeto.
- Para cada tabla sensible inventariada devuelve `matched_subject_store_rows` solo si la atribución y el conteo ya están implementados. **`null` significa no inspeccionado**; no significa cero filas. Un cero en una tabla contada tampoco acredita ausencia de copias en proveedores o archivos.
- Separa `partial_snapshot_unapproved` de `linked_count_only_not_exported` y de `not_attributed_or_exported`. Ninguno de estos estados significa fuente exportada completamente.
- Reporta pedidos pedidos por Shopify que no coinciden, cliente compartido con otras tiendas, tablas sensibles no clasificadas, ausencia de tablas declaradas y proveedores sin reconciliar.
- Nunca devuelve ID original de cliente, emails, teléfonos, nombres, direcciones, cuerpos de mensajes, datos de automatizaciones, tokens, material cifrado, claves ni enlace descargable.

Se registró la ruta en el contrato de API, con pruebas de autenticación, separación de dos tiendas, selección de pedido inexistente, falta de firma, identidad ambigua, ID incorrecto, respuesta sin PII y garantía de que la revisión no crea archivos cifrados.

### Interpretación

| Clase | Qué hay | Qué falta |
|---|---|---|
| 6 tablas locales | Conteo por cliente y tienda; snapshot cifrado parcial disponible solo a Python de confianza | Proveniencia de todos los campos, datos compartidos, consistencia de datos y validación de integridad de la exportación |
| 5 tablas automatización | Conteos por enlaces verificados de campaña/flujo | Exportar los payloads pertinentes; otros registros huérfanos/legacy y tareas/colas |
| Resto de superficies ORM | Inventariadas como desconocidas | Resolución exacta de sujeto y tienda, definición de campos, prueba de cobertura |
| Proveedores externos, archivos, IA, logs, backups | Áreas listadas | Evidencia comprobable de localización, procedencia, retención, exportación y borrado |

## Bloqueos

Las respuestas mantienen `complete=false`, `live_export_authorized=false`, `merchant_delivery_authorized=false` y `shopify_fulfillment_complete=false` sin excepción. No se cambia el proceso productivo de entrega, que continúa **synthetic-only**; ninguna autorización puede inferirse de los conteos.

Antes de activar exportación real, los siguientes PR deben cerrar la cobertura por fuente/columna, revisión legal/consentimiento, excepciones de retención y terceros, concurrencia de lecturas, empaquetado cifrado/firmado en entorno apropiado, identidad del destinatario y pruebas E2E con tienda de desarrollo.

### Pruebas

```bash
cd backend
pytest -q tests/test_shopify_privacy_local_processor.py tests/test_shopify_privacy_inventory_coverage.py tests/test_route_contract.py
```

No usar esta ruta para exportar CSV o construir un endpoint de descarga. El reporte no contiene datos de sujetos; tampoco sustituye la evaluación de Shopify Partner ni la verificación de la app liberada.
