# DIAGLOB — Integridad de procedencia en exportaciones de automatización Shopify

**Alcance:** protección de los cinco tipos de registros de automatización que ya disponían de extracción cifrada **solo para fixtures SQLite en memoria**, con reconciliación por cliente/tienda. No se activa una exportación real ni se declara un derecho de acceso cumplido.

## Hallazgo

Los conteos y extracciones anteriores se vinculaban principalmente al `customer_id` compartido dentro de DIAGLOB y a la tienda declarada en una campaña o ejecución. Cuando un registro hijo apuntaba a una versión de flujo o ejecución con organización/tienda inconsistente, podía **desaparecer por un filtro** en lugar de levantar un error de cobertura. El SHA del fichero cifrado o la igualdad de conteos entre dos consultas iguales no demuestra que las referencias padre sean correctas.

## Cambio

- Nuevo `shopify_privacy_automation_parent_integrity.py`: comprobación de procedencia, solo lecturas de identificadores, para una tienda/cliente ya resueltos exactamente.
- **Campañas:** cada ejecución de destinatario asociada a la campaña de esa tienda debe referenciar un run cuya organización coincida con la campaña. Una clave con drift bloquea el proceso.
- **Flujos:** la ejecución y su flujo definido deben tener la misma tienda/organización; la versión referenciada ha de pertenecer al flujo y a su organización; la versión y organización del destinatario deben coincidir con su ejecución.
- Se analiza por la tienda declarada en el **flujo padre o en el run**, para que un run dañado no quede oculto cuando un único filtro lo excluye.
- El control se ejecuta antes de devolver los conteos de `inspect_shopify_automation_privacy_impact`; por tanto, protege también la extracción cifrada sintética y el endpoint de reporte que reutilizan dicho inspector.
- Las consultas de comprobación seleccionan únicamente IDs. No leen contenidos de mensajes, direcciones, nombres, plantillas, payloads, ni claves.
- Ante desalineación: `AUTOMATION_CAMPAIGN_PARENT_TENANCY_MISMATCH` o `AUTOMATION_FLOW_PARENT_PROVENANCE_MISMATCH`; el preflight operativo comunica `AUTOMATION_PROVENANCE_UNVERIFIED` y la extracción sintética queda bloqueada.

## Regresiones

```bash
cd backend
pytest -q tests/test_shopify_privacy_automation_provenance.py tests/test_shopify_privacy_local_processor.py
```

Se prueban drift de campaña/organización, flujo/tienda, versión padre, destinatario/organización, versión destinatario, errores de conteo sin exponer PII y denegación de extracción. Los escenarios de cliente compartido con otra tienda, cliente no resuelto y extracción cifrada de pruebas existentes continúan como pruebas de no regresión.

## Puertas aún abiertas

No implica cobertura completa de `automations` legacy, colas no vinculadas, archivos, proveedor WhatsApp, IA/Copilot, triggers, plantillas compartidas o respaldos. Esos orígenes permanecen **no reconciliados** en el inventario. La lógica de producción sigue bloqueada para exportar PII: falta aprobación jurídica, cobertura por campos, evidencia de destinatario autenticado, reconciliación con proveedores y verificación E2E, además del plan de entrega y purga.

**No modificar el estado de fulfillment ni activar API de descarga con este PR.**
