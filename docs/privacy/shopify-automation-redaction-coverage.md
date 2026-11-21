# Shopify — depuración de automatizaciones, por tienda y comprador

**Estado:** cambio propuesto, sin mutaciones AWS ni casos productivos. No constituye cumplimiento de proveedores externos.

## Superficies estructuradas ahora cubiertas

Tras validar webhook HMAC, tienda y sujeto, preview, política y dos firmas Ed25519, el flujo `execute_local_privacy_redaction` añade un paso transaccional de `scrub_shopify_automation_scope` **antes** de borrar las relaciones Shopify del comprador. Sólo actúa sobre filas con relaciones de campaña/run/flujo que acreditan `organization_id` y `store_id`, y sobre el `customer_id` exacto en `customers/redact`. Para `shop/redact`, todas las filas de esa tienda quedan dentro del alcance.

- `AutomationAudienceMember`: elimina la membresía únicamente en campañas de la tienda afectada.
- `AutomationRecipientExecution`: deja los trabajos `queued`, `retry_wait` y `processing` fuera de envío; `sending` se marca ambiguo. Elimina `rendered_message`, `template_data`, mensajes de error, IDs de proveedor y estados de reintento/lease; conserva metadatos mínimos.
- `AutomationDeliveryAttempt`: elimina IDs del proveedor y errores potencialmente personales.
- `AutomationFlowRecipientExecution`: detiene ejecuciones activas/esperando, limpia token de claim y estados de próximo envío.
- `AutomationNodeExecution`: elimina `extra_data`, IDs de proveedor y mensajes de error.
- `AutomationFlowRun.trigger_context`: borra cuando toda la ejecución pertenece al sujeto solicitado; si tiene otros destinatarios y la procedencia no puede separarse, **preserva el contexto y registra un bloqueo**. En `shop/redact` todo el run pertenece a la tienda y se limpia.

El servicio no hace `commit`; el resultado y el audit `automation_redaction_executed` entran en la misma transacción que redacción SQL y tombstones. Error transaccional implica rollback de los cambios.

## Garantías y límites

- No se utilizan correos, teléfonos ni texto de mensajes para atribuir propiedad de los datos a una tienda.
- El mismo comprador asociado a otra tienda conserva sus campañas, datos y ejecuciones ajenas.
- Se reportan `possible_inflight_deliveries` y `mixed_recipient_contexts_unverified` para revisión independiente. No se afirma que una llamada en vuelo al proveedor pueda revertirse.
- No cubre campañas legacy, Copilot sin FK de comprador, objetos S3/Bedrock, Google, entregas ya aceptadas por WhatsApp o proveedores, ni restore de respaldos.
- No se cambia `fulfillment_complete=false`; los controles externos e históricos continúan abiertos.
- Los tombstones de `local_customer` del PR complementario bloquean recontacto desde colas antiguas si el perfil Shopify ya fue borrado.

## Validación

```bash
cd backend
pytest -q tests/test_shopify_privacy_automation_redaction.py tests/test_shopify_privacy_local_execution.py
```

Se requieren fixtures E2E de workers con carreras `sending`/restore y evidencia real de terceros antes de certificación de caso.
