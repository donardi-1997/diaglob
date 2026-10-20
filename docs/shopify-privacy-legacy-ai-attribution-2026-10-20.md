# DIAGLOB — Shopify: atribución de automatizaciones heredadas e IA

**Estado:** inspección de procedencia solo de lectura, por caso de Shopify firmado; no exporta, entrega ni elimina información personal. Integrado en el endpoint interno ya existente:
`GET /api/internal/shopify/privacy/cases/{request_id}/export/provenance`.

## Hallazgo de esquema

- El modelo `AutomationExecution` almacena `input_json`, `result_json` y `error_message` (texto libre potencialmente personal), pero **no tiene una FK de cliente**. Su `store_id` y la del `Automation` padre son opcionales; una ejecución organizacional puede incluir datos de cualquier tienda.
- Las tablas de Copilot/IA, fuentes de conocimiento, riesgos y fulfillment pueden contener mensajes, prompts, perfiles derivados y referencias indirectas. La presencia de una columna `customer_id` o `store_id` por sí sola **no prueba** propiedad de un comprador Shopify específico.

## Comportamiento nuevo

El módulo `shopify_privacy_legacy_ai_attribution.py` se ejecuta solo después de comprobar que la solicitud es válida, tiene recepción firmada, alcance de cliente/tienda verificable y sigue pendiente.

- Cuenta exclusivamente los **IDs** de ejecuciones heredadas de la misma organización y clasifica cuatro poblaciones: ambos identificadores de tienda concordantes, solo tienda en automatización, solo tienda en ejecución y sin tienda en ninguno (alcance organizacional).
- Si hay contradicción de organización entre automatización padre y ejecución, se rechaza con `LEGACY_AUTOMATION_PARENT_TENANT_MISMATCH`. Si una ejecución de la tienda aparece asociada a una automatización de otra tienda, con `LEGACY_AUTOMATION_PARENT_STORE_MISMATCH`.
- No carga `input_json`, `result_json`, `error_message`, mensajes, datos de proveedores, nombres ni contactos; nunca intenta vincular por email/teléfono o coincidencias de texto.
- Las tablas de IA, riesgo y fulfillment se describen mediante su **esquema**: si existe llave de tienda, si hay FK directa al cliente, presencia de modelo y **estado de atribución todavía no verificado**. No se consultan sus filas.
- Los resultados se agregan a `unattributed_legacy_and_ai` del reporte ya autenticado y su lista de blockers. `matching_subject_rows` permanece `null` (desconocido), no cero.
- No hay migraciones, endpoints nuevos, accesos públicos, mutaciones ni entrega de ciphertext. Los flags de autorización y cumplimiento siguen en `false`.

## Pruebas

```bash
cd backend
pytest -q tests/test_shopify_privacy_local_processor.py tests/test_shopify_privacy_inventory_coverage.py
```

Incluye cliente compartido entre dos tiendas, ejecuciones propias y ajenas, registros organizacionales, contradicciones de tienda/organización, ausencia de filtración de textos/JSON y estado `unverified` de IA.

## Siguientes puertas de salida

1. Definir el origen y la semántica de cada ID de cliente en automations legacy y Copilot. Cuando no exista una FK verificable, **no** inferir titularidad a partir de payloads JSON o texto libre.
2. Diseñar una relación/tabla de procedencia persistente que se escriba **en el momento de generación de los eventos** (tenant, tienda, sujeto externo Shopify, origen, retención, firma y versión). No reconstruir históricos ambiguos por heurísticas.
3. Revisar qué prompts, respuestas, resúmenes y perfiles pueden contener datos de terceros; aplicar minimización y exclusiones legales.
4. Reconciliar datos fuera del servidor (Bedrock/LLM, WhatsApp/email, colas, S3, logs y backups), autenticar destinatario y ejecutar pruebas E2E antes de activar operaciones reales.

**Este cambio reduce falsos negativos en inventario; no certifica cobertura GDPR ni autoriza exportación/erasure live.**
