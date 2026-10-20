# Shopify P0 — Inventario inicial A1/B1 y mapa de permisos B2

**Base analizada:** `main` @ `fc8baf1a402fbc2aa6d50b331e168c30a820fce7`  
**Estado:** **INICIADO / INVENTARIO PARCIAL**, solo lectura del repositorio. No representa un censo completo de datos desplegados ni evidencia de permisos aprobados en Shopify Partner.  
**Objetivo:** identificar el flujo fuente → campo → aplicación → modelo/salida → alcance de exportación/borrado y asociarlo a los permisos estrictamente necesarios.

> **Advertencia de procedencia:** varios registros `Customer`, `Order` y conversaciones pueden originarse también en canales no Shopify. La presencia de un campo en una tabla o una mutación que ENVÍA PII a Shopify no demuestra, por sí sola, que Shopify esté proporcionando ese mismo campo mediante Admin API. La procedencia por registro debe conservarse para no borrar información de otros canales.

## 1. Inventario de flujos y datos comprobados en código

| ID | Origen / operación | Datos observados | Destino / persistencia observada | Alcance y consecuencia para privacidad/PCD | Evidencia |
|---|---|---|---|---|---|
| F01 | Admin GraphQL: `shop { name, myshopifyDomain, currencyCode }` | Metadatos de comercio sin campos de consumidor | Resultado de prueba de conexión y comercio asociado | Scope del comercio; no justifica leer nombre/correo de compradores | [`shopify_sync.py:23-30,153-184`](../backend/app/shopify_sync.py#L23-L30) |
| F02 | Admin GraphQL: `products`, variantes e inventario | `id`, `title`, `handle`, `descriptionHtml`, imagen, SKU, precio, `inventoryQuantity`, disponibilidad | `products`, variantes relacionadas por `organization_id` y `store_id` | Catálogo; no se observan campos directos de cliente en esta consulta | [`shopify_sync.py:34-104,187-210,304-350`](../backend/app/shopify_sync.py#L34-L104) |
| F03 | Shopify `orders/create`, `orders/updated`, `orders/cancelled` firmados | Payload de pedido; `customer.id/email/phone/first_name/last_name`, `shipping_address`, `billing_address`, notas, estado, line items | `customers`, `customer_store_profiles`, `orders`, `order_items`; relaciones por organización/tienda/pedido | **Entrada Shopify con PII real**; puede quedar almacenada aun sin una consulta directa `customers` de GraphQL | [`shopify_webhook_service.py:40-44,98-160,318-350,457-605,648-675`](../backend/app/services/shopify_webhook_service.py#L457-L605) |
| F04 | GraphQL `orderCreate` (pedido COD, orden creada desde DIAGLOB) | **DIAGLOB → Shopify:** `customer_phone`, `customer_email`, dirección de envío con nombre/apellidos/ciudad/teléfono. Respuesta solicitada incluye `order.email` y `order.phone`, aunque el flujo de COD mostrado utiliza únicamente ID/número | `orders` y `order_items`; `orders.shipping_address` es JSON | Separar PII **enviada** a Shopify de PII **solicitada en la respuesta**; minimizar campos de la selección GraphQL innecesarios | [`shopify_cod_orders.py:51-81,174-235`](../backend/app/shopify_cod_orders.py#L51-L81), [`shopify_client.py:198-223`](../backend/app/shopify_client.py#L198-L223) |
| F05 | GraphQL `draftOrderCreate` | **DIAGLOB → Shopify:** artículos y, opcionalmente, `customer_email` / `customer_name` proporcionados a este flujo; respuesta: ID, número, importe, `invoiceUrl`, IDs de line item | `orders.shopify_draft_order_id`, `orders.invoice_url` y demás campos del pedido | No inferir permiso de lectura `read_customers` únicamente por este envío | [`shopify_orders.py:420-456`](../backend/app/shopify_orders.py#L420-L456), [`shopify_client.py:168-194`](../backend/app/shopify_client.py#L168-L194) |
| F06 | GraphQL `order(id)` → `fulfillmentOrders`; mutación `fulfillmentCreate` | ID/estado de pedido y fulfillment, líneas, seguimiento y proveedor de transporte. `notifyCustomer` marca aviso | Referencias de fulfillment, envíos y seguimiento locales | Lectura/escritura de pedidos y fulfillment con justificación operativa. Auditar trazabilidad del envío a proveedores logísticos | [`shopify_fulfillment.py:23-69,240-265`](../backend/app/services/shopify_fulfillment.py#L23-L69) |
| F07 | Webhooks obligatorios `customers/data_request`, `customers/redact`, `shop/redact` | Identidad de tienda y selectores de cliente/pedido incluyendo ID, correo/teléfono cuando llegan | `shopify_privacy_requests.selector_encrypted`, `shopify_privacy_work_items`, auditoría e identidad de tienda | Recepción cifrada y cola; **no equivale a entrega/borrado real** | [`shopify_compliance_webhooks.py:35,75-83`](../backend/app/services/shopify_compliance_webhooks.py#L35-L83), [`model_domains/shopify_privacy.py:14-44,141-163`](../backend/app/model_domains/shopify_privacy.py#L14-L44) |
| F08 | Flujo de solicitudes de privacidad, cobertura y exportación sintética | Campos de `customers`, `orders`, conversaciones y checkout; área de IA, automatizaciones, proveedores y backups | Inventario parcial de tablas y manifest; extractor `SQLite :memory:` únicamente | **P0 abierto**: la función de extracción sintética rechaza BD persistente; retorno de procesamiento `fulfillment_complete=False` | [`shopify_privacy_scoped_extraction.py:46-76`](../backend/app/services/shopify_privacy_scoped_extraction.py#L46-L76), [`shopify_privacy_processing.py:48-66`](../backend/app/services/shopify_privacy_processing.py#L48-L66) |

## 2. Superficies de persistencia y propiedad

| Superficie | Campos / relación identificada | Atribución | Estado para exportar / borrar |
|---|---|---|---|
| `customers` | `name`, `phone`, `email`, `country_code`, `organization_id` | **Compartido por organización**; sin `store_id` propio | **Sin cobertura total.** No borrar fila compartida automáticamente cuando una sola tienda solicita redacción. [Modelo](../backend/app/model_domains/customers.py#L19-L76) |
| `customer_store_profiles` | `customer_id`, `organization_id`, `store_id`, `external_customer_id`, gasto y conteos | Tienda/cliente; Shopify ID vincula el sujeto | Parcial; enlace de sujeto crítico. [Modelo](../backend/app/model_domains/customers.py#L83-L151) |
| `orders` | `customer_id`, `shopify_order_id`, `note`, `shipping_address` JSON, `invoice_url`, eventos y estado | Organización+tienda+pedido | Parcial; `shipping_address` contiene PII y requiere política de retención por pedido. [Modelo](../backend/app/models.py#L699-L869) |
| `order_items` | Artículos y referencias externas | Vía pedido y tienda | Parcial; verificar que su procedencia corresponde al pedido Shopify. [Cobertura](../backend/app/services/shopify_privacy_field_coverage.py#L20-L60) |
| `conversations` + `messages` | Texto, preview y referencias al cliente | Tienda/conversación, cliente posiblemente compartido | Parcial: contenido libre puede incluir PII no estructurada. [Cobertura](../backend/app/services/shopify_privacy_field_coverage.py#L20-L60) |
| `conversational_checkouts` | `customer_name`, `phone`, `address_raw`, `address_line`, ciudad y referencia de entrega | Organización+tienda+cliente | Parcial; verificar origen Shopify vs WhatsApp/otros. [Modelo](../backend/app/model_domains/conversational_checkout.py#L46-L149) |
| `commerce_connections` | `external_store_url`, scopes y tokens de acceso/refresh cifrados | Organización+tienda+proveedor | Contiene credenciales; no deben incluirse en entregas de privacidad al consumidor. Revisar revocación/retención tras `shop/redact`. [Modelo](../backend/app/model_domains/commerce_integrations.py#L15-L55) |
| IA, automatizaciones, conocimiento, colas y reportes de riesgo | Sesiones/chat/herramientas, fuentes de conocimiento, campañas, entregas, análisis | Varias tablas con alcance mixto | **Descubiertas como parcialmente/no cubiertas** por inventario estático; requieren dueños, vínculo a Shopify y control de procesadores. [Inventario existente](../backend/app/services/shopify_privacy_inventory_coverage.py#L33-L74) |
| S3, sistemas de mensajería, logística, proveedores externos, logs, backups | Réplicas y derivados potenciales (no verificados) | Fuera de SQL / contrato de servicios | **NO AUDITADOS en runtime**; no afirmar supresión total hasta obtener evidencia. [Áreas externas](../backend/app/services/shopify_privacy_inventory_coverage.py#L65-L74) |

### Riesgo de atribución que requiere prueba específica

[`_upsert_customer`](../backend/app/services/shopify_webhook_service.py#L457-L571) busca primero el identificador Shopify en `CustomerStoreProfile` de la tienda, **pero si no lo encuentra permite reutilizar un `Customer` de la misma organización por teléfono o correo** (líneas 526–544), y después actualiza nombre/teléfono/correo de esa entidad compartida (líneas 556–563).

Esto **puede generar acoplamiento entre dos tiendas**. No constituye por sí solo evidencia de lectura no autorizada, pero bloquea cualquier diseño de redacción que asuma un registro `Customer` exclusivo de una tienda. Antes de modificar este comportamiento, reproducir con fixtures multi-shop y definir tratamiento correcto de identidad compartida, datos de otras fuentes y actualización de información.

### Riesgo confirmado de cumplimiento

[`shopify_privacy_inventory_coverage.py:35-62`](../backend/app/services/shopify_privacy_inventory_coverage.py#L35-L62) clasifica varias superficies como `uncovered`; [`shopify_privacy_scoped_extraction.py:46-53`](../backend/app/services/shopify_privacy_scoped_extraction.py#L46-L53) prohíbe extracción real salvo SQLite en memoria; [`shopify_privacy_processing.py:63-65`](../backend/app/services/shopify_privacy_processing.py#L63-L65) mantiene `fulfillment_complete=False`. **A1 no puede cerrarse solamente con este inventario inicial.**

## 3. Matriz de los ocho scopes declarados (B2)

**Fuente de verdad del código:** [`shopify.app.toml:9-13`](../shopify.app.toml#L9-L13), [`shopify_oauth.py:11-20`](../backend/app/shopify_oauth.py#L11-L20). **Pendiente:** confirmar scopes efectivos de versión activa y permisos concedidos en tienda de desarrollo.

| Scope declarado | Operación comprobada en source | ¿Necesidad demostrada en estos archivos? | Decisión provisional |
|---|---|---|---|
| `read_products` | `products` / variantes vía GraphQL | Sí, para catálogo | Mantener hasta verificar características publicadas |
| `read_inventory` | `inventoryQuantity` en variantes | Probable para stock; probar granularidad/alcance | Mantener provisionalmente |
| `read_customers` | **No se identificó una consulta Admin `customers`** en el conjunto revisado. Los webhooks de pedidos sí aportan datos del cliente | **No demostrado para lectura directa**; no equivale a ausencia de uso en todo el repositorio | **Candidato a reducir**, sujeto a inspección exhaustiva y prueba E2E |
| `read_orders` | `order(id)` en seguimiento/fulfillment | Sí para la funcionalidad inspeccionada | Mantener provisionalmente |
| `write_orders` | `orderCreate` COD | Sí para creación de órdenes de esa función | Confirmar si la característica va en versión pública |
| `write_draft_orders` | `draftOrderCreate` | Sí para el flujo de borradores | Confirmar si la característica va en versión pública |
| `read_merchant_managed_fulfillment_orders` | `fulfillmentOrders` con IDs y líneas | Sí para fulfillment | Mantener si la función se ofrece |
| `write_merchant_managed_fulfillment_orders` | `fulfillmentCreate` | Sí para fulfillment | Mantener si la función se ofrece |

**Sin decisión final:** no modificar ni desplegar scopes con base exclusivamente en esta muestra. Shopify puede redactar campos protegidos incluso cuando el permiso del recurso esté concedido.

## 4. Campos de identificación personal: matriz provisional B1/B3

| Campo | Confirmación de fuente | Uso confirmado | Evaluación |
|---|---|---|---|
| Nombre y apellidos | Shopify webhook de pedidos (`customer`, `shipping_address`, `billing_address`) | `Customer.name`, `orders.shipping_address`; también DIAGLOB envía datos a `orderCreate` | **Campo protegido: inventariar/justificar acceso**, no declararlo innecesario sin reducir el consumo |
| Correo | Shopify webhook `customer.email` / pedido `email`; GraphQL `orderCreate` pide `order.email` | `Customer.email`; creación de pedidos desde DIAGLOB envía correo opcional | **Campo protegido: verificar aprobación y necesidad de selección GraphQL** |
| Teléfono | Shopify webhook `customer.phone` y dirección; GraphQL `orderCreate` pide `order.phone` | `Customer.phone`, `orders.shipping_address`; envío de pedido COD | **Campo protegido** |
| Dirección | Shopify webhook `shipping_address` | `orders.shipping_address` JSON; DIAGLOB también ENVÍA dirección a pedido COD | **Campo protegido** |
| ID Shopify de cliente | Shopify webhook `customer.id` | `CustomerStoreProfile.external_customer_id` y selectores de privacidad | Identificador con riesgo de vinculación; requiere minimización y controles de identidad |
| Notas de pedido / texto libre | Shopify webhook `note` | `orders.note` | Puede contener PII de forma no estructurada; revisar retención/sanitización |

**Recomendación provisional:** la declaración actual «No necesita acceso a datos de clientes protegidos» es **incompatible como hipótesis de diseño** con el consumo de nombre/correo/teléfono/dirección de webhooks Shopify que persisten en DIAGLOB. Sin embargo, **solo Partner puede confirmar** el tipo de acceso PCD y los campos aprobados en la versión activa. Comparar el dashboard con la función publicada antes de solicitar o retirar permisos.

## 5. Próximas comprobaciones para terminar A1/B1 (tareas concretas)

- [ ] Auditar el resto de rutas Shopify, webhooks, workers, integraciones y consultas a Admin API para descartar otros `customers`/campos y determinar si `read_customers` es prescindible.
- [ ] Trazar las dependencias de las entidades `Customer`, `Order`, `Conversation` y `ConversationalCheckout` hacia IA, automatizaciones, analítica, archivos y proveedores; asignar estado `covered` o `uncovered` por **campo**, no solo tabla.
- [ ] Construir un fixture de dos tiendas Shopify con mismo correo/teléfono y Customer compartido para verificar vinculación y política de redacción sin contaminación.
- [ ] Confirmar origen de datos externo frente a entrada directa de DIAGLOB; no exportar/borrar datos de otros canales automáticamente.
- [ ] Documentar retención legal de pedidos, respaldos, mensajes y logs, más contratos de encargados.
- [ ] Inspeccionar Partner Dashboard sin exponer secretos: versión activa, permisos y campos protegidos solicitados/aprobados; recuperar evidencia de callbacks firmados.
- [ ] Definir decisiones de mínima funcionalidad pública: cuál de COD, borradores, automatización y fulfillment se anuncia realmente.
- [ ] Convertir la matriz a pruebas automáticas de aislamiento y de rechazo de campos no autorizados; actualizar el plan de los issues #266 y #267.

## Criterio para marcar A1/B1/B2 completo

Cada flujo y fuente relevante tiene **origen, propietario, scope, operación/campo, persistencia, destino externo, base/política de retención y acción de exportación/redacción** respaldados; ninguna superficie con datos Shopify permanece sin clasificación; `read_customers` tiene decisión final con prueba; acceso PCD coincide con la versión activa de Shopify. Hasta entonces, estado **PARCIAL**.

**No se han ejecutado pruebas, no se ha consultado la BD de producción, no se han modificado planes, permisos ni webhooks activos.**
