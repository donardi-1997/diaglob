# DIAGLOB — Procedencia al generar ejecuciones de automatización

**Alcance de este PR:** registrar de forma persistente la procedencia mínima de *nuevas* ejecuciones heredadas. No exporta datos personales, no aplica supresión, no habilita un endpoint ni altera la clasificación de casos GDPR completados.

## Cambios

- `automation_execution_provenance` (Alembic `ab6c73d4e5f9`): una fila única por ejecución; organización, tienda, ID de cliente DIAGLOB opcional, origen contextual, estado del vínculo, versión y fecha. Sin email/teléfono/nombre, identificador externo Shopify ni contenido JSON de evento.
- El motor `execute_automation` valida su organización y tienda antes de crear la ejecución; la procedencia se inserta **en la misma transacción antes de ejecutar acciones** y de guardar el estado final. Esto protege contra inserciones futuras sin la tabla una vez desplegada la migración.
- `run_automations_for_event`, `emit_event` y `safe_emit_event` preservan el `store_id` del evento, incluso para una automatización organizacional. Se admite `subject_customer_id` solo como parámetro explícito de un llamador confiable; nunca se extrae de `payload`, `event_id`, teléfono, correo o cuerpo de mensaje.
- Un `subject_customer_id` solo se persiste si existe una correspondencia **única** con `CustomerStoreProfile` y el cliente pertenece a la misma organización/tienda. Incluso en ese caso su vínculo es `local_profile_shopify_unverified`: **NO** es una identidad Shopify verificada.
- Ausencia de contexto: `subject_not_asserted` o `store_and_subject_not_asserted`, siempre sin customer ID. Divergencia de tienda/organización o perfil ajeno produce un error con código neutro antes de acciones.
- No se ejecuta **ningún backfill** de ejecuciones previas. Las ejecuciones históricas permanecen desconocidas para exportación de clientes Shopify.

## Pruebas

```bash
cd backend
pytest -q tests/test_automation_execution_privacy_provenance.py tests/test_automations.py tests/test_automations_hardening.py tests/test_alembic_heads.py
```

Incluye tienda concreta, automatización organizacional disparada por una tienda, comprador compartido entre tiendas, ID explícito con perfil verificable, JSON que contiene datos personales pero sin ID explícito, tienda/organización cruzadas, historial sin backfill y única revisión de Alembic.

## Despliegue y límites

1. **Aplicar migración antes de desplegar procesos que ejecuten automatizaciones.** Si falta la nueva tabla, la inserción de procedencia fallará y deberá detenerse la ejecución; no hay escritura alternativa sin evidencia.
2. Auditar primero las rutas que despachan eventos y conectar, una por una, un `subject_customer_id` derivado de un ID interno comprobado **antes de construir payloads**. No incluirlo por heurísticas.
3. Un perfil local no acredita consentimiento, identidad del Shopify shop ni titularidad del sujeto externo; requiere contraste independiente con recibos Shopify y versiones de tienda.
4. No mantener eventos privados en logs, no reinterpretar procedencia de otro tenant y evitar restauración sin reconciliación de supresiones.
5. No se han reconciliado datos de Bedrock/IA, archivos externos, colas o proveedores, ni aprobado conservación legal. `live_export_authorized=false` y `fulfillment_complete=false`.

**Este PR deja una base persistente, no cierra la exportación GDPR real ni los requisitos de Shopify Partner.**
