# DIAGLOB — Expediente de acceso a Protected Customer Data para Shopify Partner

**Fecha:** 2026-10-20 · **Estado:** BORRADOR TÉCNICO, NO PRESENTADO, NO APROBADO.

**Aplicación existente:** DIAGLOB · Shopify App GID `gid://shopify/App/416524435457` · Client ID público `c5fc9aed710462d41767477fa9e595c0`. No crear otra app ni solicitar el permiso `read_customers` sin demostrar un nuevo uso.

**Conclusión de clasificación:** **Nivel 2** (se procesan datos de pedido vinculados al comprador, incluidos nombre, dirección, correo y teléfono). Shopify exige solicitar el acceso a datos protegidos **y** los campos identificatorios concretos, con justificación mínima y medidas de Nivel 1 + Nivel 2. La selección de campos para desarrollo puede realizarse sin revisión de publicación, pero **no** equivale a aprobación pública. Fuente: https://shopify.dev/docs/apps/launch/protected-customer-data

## 1. Texto base para el formulario (revisar antes de enviarlo)

**Protected customer data — reason for access (EN):**

> DIAGLOB enables merchants to synchronize and manage Shopify order and fulfillment workflows. The app processes order-linked customer identifiers and contact/shipping information supplied through merchant-authorized order events to associate orders with the correct shop and customer, display fulfillment context to authorized merchant staff, and support delivery operations. DIAGLOB does not require bulk Customer API reads: its requested Admin API scopes exclude `read_customers`. Customer information is not requested to create a separate consumer profile unrelated to merchant operations. Personal data handling is subject to store/tenant access restrictions, purpose limitation, and the merchant's privacy obligations. Additional processing for automations, external delivery providers, deletion, export, and retention requires further validation before public release.

**Advertencia:** la frase anterior describe el diseño y las finalidades propuestas. No constituye una certificación de cumplimiento de todos los flujos. Confirmar el catálogo funcional y legal antes de usarla literalmente.

| Campo Shopify a solicitar | Evidencia concreta del código | Justificación candidata (EN) | Validación de minimización |
| --- | --- | --- | --- |
| **Name** (nombre y apellidos) | `shopify_webhook_service.py::_upsert_customer` lee `first_name`, `last_name` y nombre de destinatario; `_shipping_address` conserva `customer_name` | `To identify the consignee associated with an order so authorized merchant staff can verify the delivery recipient and order-fulfillment details.` | Verificar que las pantallas de fulfillment requieren nombre completo y no solo referencia del pedido |
| **Address** (dirección; línea 1/2, ZIP y campos cubiertos por Shopify) | `_apply_order_fields` persiste `order.shipping_address`; `_shipping_address` extrae `address1`, `address2`, ciudad, región, país, `zip` | `To provide the order's shipping destination to authorized fulfillment and last-mile delivery workflows, where the merchant requests physical delivery.` | Geolocalización del comprador no está demostrada; no atribuir usos de latitud/longitud no observados. Confirmar máscara/redacción en pedidos no entregables |
| **Email** | `_upsert_customer` lee `customer.email` / `order.email`; se conserva en `Customer.email` y `order.shipping_address.email` | `To associate order-linked contact details with the correct merchant and allow authorized order-related communications when required by the merchant's workflow.` | **Pendiente:** demostrar comunicación transaccional real y necesidad mínima; evitar alegar campañas de marketing o comunicación automática sin opt-in y evidencia |
| **Phone** | `_upsert_customer` lee teléfono de customer/shipping/billing y `_shipping_address.phone`; se conserva en `Customer.phone` | `To support merchant-authorized delivery coordination and consignee contact for shipping orders when phone contact is required.` | **Pendiente:** comprobar necesidad por transportista/ruta y si debe ser opcional por funcionalidad; no afirmar que es indispensable para todas las tiendas |

**Adicionales a clasificar antes de enviar:** Shopify customer ID, order ID, order notes (texto libre potencialmente PII), shipping company, customer/store profiles, conversaciones y mensajes, automatizaciones, archivos, proveedores y backups. Aunque no todos sean cuatro campos individuales de Nivel 2, deben figurar en el inventario de PCD y políticas de finalidad/retención.

## 2. Trazabilidad entre fuente y finalidad

- Código que recibe Shopify: `backend/app/services/shopify_webhook_service.py`, funciones `_upsert_customer`, `_shipping_address` y `_apply_order_fields`.
- Persistencia: `backend/app/model_domains/customers.py`, tablas `customers` y `customer_store_profiles`; `orders.shipping_address` es un campo estructurado de pedido.
- `Customer` se comparte a nivel organización. El identificador Shopify por tienda se encuentra en `CustomerStoreProfile`; hay vinculación por correo/teléfono bajo ciertas condiciones. La reutilización de identidad entre tiendas necesita revisión humana y pruebas de aislamiento.
- Lecturas con autorización por organización/tienda: `backend/app/api/customers.py`; control implementado tras PR #274. La auditoría incluye registros `CUSTOMER_PCD_READ` sin datos identificatorios, pero no hay prueba de retención/centralización de logs.
- `SHOPIFY_SCOPES` / `shopify.app.toml`: siete scopes declarados; se retiró lectura masiva `read_customers`. Esto **no elimina** el tratamiento de datos a través de órdenes y webhooks.
- Seguridad de credenciales: `backend/app/shopify_security.py` utiliza Fernet con clave en entorno. Esto **no acredita** cifrado de todas las columnas PCD, discos, respaldos ni recuperación.
- Solicitudes de privacidad: `customers/data_request`, `customers/redact`, `shop/redact` declaradas en TOML; recepción/validación y partes de inventario/entrega sintética existen. **Exportación y borrado real de extremo a extremo no habilitados ni verificados.**

## 3. Data protection details — lista de afirmaciones verificables

| Requisito | Evidencia disponible | ¿Se puede marcar cumplido? |
| --- | --- | --- |
| Minimizar datos y finalidad explícita | Inventario parcial de campos, siete scopes en código, flujos Shopify pedidos | **NO**, falta aprobar finalidades, datos derivados y procesadores |
| Información al comerciante / política y acuerdo de datos | Documentos técnicos y contratos/políticas pendientes de contraste | **NO**, revisar URLs publicadas y acuerdos vigentes |
| Consentimiento, opt-out y perfilamiento/automatizaciones | Hay automatizaciones y referencias a clientes | **NO**, comprobar base legal, exclusiones y decisiones significativas |
| Retención de datos | Borrador de categorías; S3 con versionado pero sin lifecycle | **NO**, decisiones legales, backups y expedientes de borrado abiertos |
| Cifrado en tránsito y reposo | URLs HTTPS, cifrado tokens Fernet, un bucket SSE-AES256 | **NO**, falta comprobación de bases, disco/backup y tránsito de todos los proveedores |
| Backups cifrados | Snapshots Lightsail automáticos activados recientemente, no acreditan cifrado ni recuperación de PostgreSQL | **NO**, demostrar cifrado, restore y retención |
| Separación test y producción | Shopify POC es tienda de desarrollo; backend de DIAGLOB opera en producción | **NO**, falta probar aislamiento completo y ausencia de PII de prod en pruebas |
| DLP y controles de acceso staff | Autorización por roles/tienda y pruebas sintéticas | **NO**, inventario de endpoints/proveedores y pruebas E2E |
| Contraseñas robustas y cuentas staff | Sin evaluación completa de política vigente en este expediente | **NO**, revisar autenticación actual de la plataforma |
| Logging de acceso PCD | Eventos locales `CUSTOMER_PCD_READ` | **NO**, falta evidenciar cobertura, almacenamiento, revisión y retención |
| Respuesta a incidentes | Documentación operacional preliminar | **NO**, verificar política aprobada y simulacro |
| Cumplimiento de GDPR webhooks | HMAC, inbox, reconciliación, fixtures | **NO**, fulfillment real incompleto |

**Regla obligatoria:** nunca seleccionar «Yes/Compliant» para una medida sin evidencia operativa suficiente; no adjuntar datos reales ni secretos al formulario. La declaración es una atestación empresarial/jurídica, no se completa automáticamente desde GitHub.

## 4. Procedimiento Partner

1. Abrir la aplicación DIAGLOB **existente** en Shopify Partner / Dev Dashboard y verificar Client ID `c5fc9aed710462d41767477fa9e595c0` y método de distribución.
2. Ir a **API access requests → Protected customer data access → Request access** (etiquetas pueden variar).
3. Seleccionar **Protected customer data** y redactar finalidad restringida al comercio.
4. Para Nivel 2 seleccionar **Name, Address, Email, Phone** *solo después* de revisar necesidad para cada flujo. Para pruebas sobre development stores Shopify no exige someter aún el app review después de selección; para distribución pública sí se aplican requisitos y revisión. Guardar selección y registrar fecha/versión.
5. Completar **Data protection details** con documentación real; no certificar controles que aún no se implementaron.
6. Capturar evidencia **sin PII ni secretos**: app ID, nivel, campos escogidos, status del pedido de acceso, versión, momento de consulta, resultado de pruebas.
7. No presentar solicitud final de App Store hasta que versión activa, scopes concedidos, controles Level 1+2 y pruebas E2E sean conformes.

**Estado en este commit:** texto y matriz listos para revisión, **no se efectuaron cambios en Partner**, no hay aprobación acreditada de Nivel 2.

## 5. Fuentes

- https://shopify.dev/docs/apps/launch/protected-customer-data
- `docs/shopify-protected-customer-data-audit-2026-10-20.md`
- `docs/shopify-pcd-security-controls-2026-10-20.md`
- `docs/diaglob-pcd-backup-recovery-plan-2026-10-20.md`
- `docs/shopify-diaglob-poc-live-scope-audit-2026-10-20.md`
