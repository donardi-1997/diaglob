# Diaglob — Auditoría de ingesta residual tras solicitudes Shopify
Fecha: 14 de octubre de 2026. Estado: PR #223, sin activación de borrado en producción.

## Qué se comprobó en el código

| Superficie | Punto de ejecución | Protección añadida | Limitación |
|---|---|---|---|
| WhatsApp entrante | `services/whatsapp_webhooks.py::process_webhook_payload` | Comprobación del teléfono HMAC antes de crear Customer, Conversation, Message o lanzar IA; segundo control por identidad local existente | No permite inferir un vínculo con un Shopify ID si Shopify no entregó teléfono y no existe perfil cruzado |
| Instagram entrante | `services/instagram_webhooks.py::process_webhook_payload` | Bloqueo de `shop/redact` y de clientes ya vinculados mediante CustomerStoreProfile | Un Instagram sender ID sin vínculo Shopify no identifica con seguridad al mismo titular; hay que registrar vínculo con origen verificable |
| WhatsApp directo | `services/whatsapp_service.py::send_message` | Bloqueo antes de extraer token y enviar al proveedor | Otros envíos fuera de este servicio requieren inventario |
| Instagram directo | `services/instagram_service.py::send_message` | Bloqueo antes de contactar Instagram | Debe preservarse el mapa consentido de identidades si se necesita localizar datos de un mismo comprador |
| IA conversacional | `services/checkout_reply_service.py`, `ai_reply_service.py` | Validación antes de inferencia en segundo plano y antes de enviar una respuesta generada | Los chats históricos, embeddings y registros de inferencia siguen sujetos a eliminación/retención independiente |
| Herramientas de agentes | `services/agent_tool_executor.py` | Oculta clientes y pedidos con supresión activa en consultas y rechaza apertura de un pedido afectado | Análisis agregado, RAG y cualquier herramienta adicional requieren inventario y contratos |
| CJ proveedor | `services/supplier_orders.py` | Bloqueo de nuevas órdenes y resincronización antes de llamar API remota | La cancelación de una orden legalmente retenida puede seguir siendo necesaria, pero nunca constituye eliminación de datos |
| CJ webhooks | `services/cj_webhooks.py` | Filtra eventos logísticos reingresados para órdenes con supresión activa, registra recibo con código `PRIVACY_SUPPRESSED` sin crear TrackingEvent/Shipment | Recibos de eventos conservan metadatos de proveedor; revisar política de retención |
| Pedidos manuales, COD, Flow Builder, fulfillment | Protecciones anteriores del PR #223 | Vigentes para rutas revisadas | Retries externos y colas no administradas deben catalogarse |
| Restores | `shopify_privacy_restore.py` y CLI del PR #223 | Comparación de checkpoints HMAC contra registro independiente del backup | El ledger externo todavía no está desplegado. Sin él la recuperación no está verificada |

## Restricciones deliberadas

- Las supresiones están en estado **staged**, salvo activación sintética SQLite bajo pytest. No hay borrado destructivo ni aprobación automática.
- HMAC de email y teléfono solo se crea cuando esos valores aparecen en el recibo firmado por Shopify. Una solicitud únicamente con `customer.id` no permite vincular de forma demostrable un contacto de Instagram o WhatsApp que use otro identificador.
- No bloquear automáticamente cuentas de Instagram no vinculadas por mera coincidencia de nombre o texto, ni eliminar registros fiscales por defecto. Es mejor marcar **identity_linkage_unresolved** para investigación con autorización que suprimir a otra persona.
- La comprobación de backup usa un checkpoint de un ledger fuera de la base restaurada. Copiar el HMAC dentro del mismo backup no aporta garantía de recuperación.
- No se puede afirmar que CJ, Meta, Shopify, proveedores email, Amazon Bedrock, Dropi, bases vectoriales, S3 ni operadores logísticos hayan borrado datos sin confirmación verificable.

## Puertas de salida restantes

1. Identidades entre canales: esquema de `CustomerIdentityLink` con consentimiento, prueba de origen, caducidad y enlace a tienda; nunca inventar enlaces por parecido textual.
2. Inventario de todos los receptores de PII: Telegram, flujos no cubiertos de agentes/herramientas, triggers webhooks de otros proveedores, RAG, logs, sistemas de pagos y exportaciones.
3. Legal: tratamiento campo a campo de facturas, pedidos, devoluciones, comunicaciones, registros de riesgo e información de marketing, con responsable, fundamento, retención y hold aprobados.
4. Externo: confirmaciones por procesador y ámbito de datos; aplicar supresión también a reenvíos/colas de terceros.
5. Recuperación: almacenar checkpoint en almacén inmutable y externo, verificar antes de permitir tráfico tras restauración, ejecutar simulacro.
6. Proceso Shopify: entrega segura para `customers/data_request`, registros auditables de finalización y revisión humana independiente.

CI ejecuta pruebas sintéticas, nunca eliminación real. **La aprobación total de cumplimiento y la fusión a producción permanecen pendientes.**
