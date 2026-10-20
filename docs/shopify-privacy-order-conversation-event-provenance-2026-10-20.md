# DIAGLOB — Atribución de pedidos y conversaciones al emitir automatizaciones

**Estado:** cambio de código construido encima del PR #284 (tabla `automation_execution_provenance`). No activa exportación o supresión de PII Shopify ni modifica el cumplimiento de un caso GDPR.

## Fuentes cubiertas

- **Pedidos recibidos de Shopify:** el servicio que procesa el webhook HMAC ya autenticado identifica el pedido guardado y verifica `organization_id`, `store_id`, `source=shopify`, el cliente del pedido y el `external_customer_id` *exacto* declarado por Shopify para esa tienda. Solo entonces pasa el ID interno como `subject_customer_id` al motor. No se deduce de email, teléfono, nombre, ni de `payload.customer_id`.
- Si no hay ID de cliente Shopify, falta perfil, la orden no pertenece a la tienda, existe ambigüedad de dos perfiles locales con el mismo ID externo, o el perfil difiere del webhook, se pasa **`None`**. El evento comercial continúa, pero la procedencia queda sin cliente atribuido.
- **WhatsApp, Instagram y Telegram:** los emisores de `conversation.created` y `message.received` verifican la conversación persistida dentro del mismo tenant/tienda y la relación de cliente con un perfil local de esa tienda. Jamás interpretan el ID del remitente de redes sociales como ID Shopify.
- Incluso con coincidencia exacta local, la tabla del PR #284 registra `subject_linkage=local_profile_shopify_unverified`. La identidad frente a Shopify no está independientemente acreditada ni autoriza extracción o borrado.

## Pruebas

```bash
cd backend
pytest -q tests/test_automation_event_subject_resolution.py tests/test_automation_execution_privacy_provenance.py tests/test_automations.py tests/test_automations_hardening.py
```

Casos: cliente compartido por dos tiendas, ID externo equivocado o ambiguo, pedido ajeno, conversación ajena/sin perfil y tres emisores de mensajería que propagan únicamente identidades derivadas de la base de datos.

## Riesgos que permanecen abiertos

- El PR #284 debe fusionarse y **su migración debe aplicarse antes de ejecutar el nuevo código**. No realizar desplegados independientes o habilitar workers con esquema antiguo.
- El flujo Shopify webhook existente puede vincular clientes por contacto durante el upsert comercial; la atribución de privacidad de este PR requiere siempre coincidencia exacta en el perfil **actual** de la tienda. No demuestra que el upsert comercial carezca de colisiones históricas; no hay backfill.
- Los eventos de pedidos creados por vías distintas a Shopify Order Webhook y cualquier ejecución de IA sin relación de sujeto verificada continúan sin atribución Shopify garantizada.
- Datos históricos, prompts/LLM, archivos, colas y proveedores externos todavía requieren procedencia, retención aprobada y pruebas E2E antes de habilitar una exportación o supresión real.
