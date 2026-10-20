# DIAGLOB — Shopify Protected Customer Data: revisión y cierre

**Fecha:** 2026-10-20. **Alcance:** inspección de código, no comprobación de permisos Partner, datos reales ni controles de AWS. **Rama:** `codex/shopify-protected-data-denials-2026-10-20`.

## Hallazgos comprobados

1. `shopify.app.toml` y `backend/app/shopify_oauth.py` solicitan ocho scopes estáticos. La configuración fuente no prueba qué scopes están activos ni concedidos a las instalaciones.
2. `backend/app/services/shopify_webhook_service.py::_upsert_customer` consume nombre, correo, teléfono e identificador del cliente desde payloads de pedidos Shopify y puede vincular perfiles entre tiendas de la misma organización. `backend/app/model_domains/customers.py` almacena nombre, teléfono y correo en la entidad compartida `Customer`; `Order.shipping_address` contiene direcciones.
3. `backend/app/shopify_security.py` usa Fernet para credenciales de conexión, pero esto **no demuestra cifrado en reposo de todas las tablas, respaldos, S3 o datos de terceros**. Verificar KMS, discos/volúmenes y accesos en el entorno real.
4. `backend/app/shopify_client.py` antes propagaba el texto original de errores GraphQL. Este cambio clasifica errores de permisos y PCD, rechaza datos parciales aunque HTTP sea 200 y devuelve códigos estáticos seguros. Cinco rutas en `backend/app/api/shopify.py` traducen esas categorías a HTTP 403 para ofrecer respuesta accionable.
5. La auditoría de privacidad `docs/shopify-p0-initial-data-inventory-2026-10-20.md` identifica persistencia y procesadores aún sin cobertura completa. La recepción de webhooks **no** equivale a exportación o borrado completo.

## Clasificación de datos y declaración propuesta

| Fuente / campo | Tratamiento observado | Categoría Shopify | Declaración recomendada |
| --- | --- | --- | --- |
| `shopify_sync`: productos, SKU, variantes, inventario | Catálogo y stock | No es PCD del comprador en estas consultas | Sin campos PCD; justificar `read_products` y `read_inventory` |
| Pedido Shopify: ID de cliente/pedido, estado, fulfillment | Seguimiento, operaciones | PCD nivel 1 | Solicitar nivel 1, si esta función permanece |
| Webhook de pedido: nombre, apellidos | Vinculación con `Customer`, entrega | Campo identificatorio nivel 2 | Declarar **nombre** si la función lo requiere |
| Webhook de pedido: correo | Vinculación, contacto | Campo identificatorio nivel 2 | Declarar **correo** si es necesario |
| Webhook de pedido: teléfono | Vinculación, contacto y entrega | Campo identificatorio nivel 2 | Declarar **teléfono** si es necesario |
| Webhook de pedido: dirección de envío/facturación | Envíos y persistencia JSON | Campo identificatorio nivel 2 | Declarar **dirección** si es necesaria |
| Pedido: notas / conversación / respuesta IA | Texto libre potencialmente identificatorio | Clasificación según contenido y procedencia | Minimizar, restringir acceso y sujetar a retención/exportación/borrado |

**Conclusión provisional:** la integración actual es compatible con una necesidad de **nivel 2**, no con la afirmación general «no requiere acceso a datos protegidos». La decisión sobre cada campo debe ajustarse a la funcionalidad que se ofrecerá y a la autorización real que se solicite en Shopify; no constituye evidencia de aprobación.

## Inventario de scopes — no desplegar cambios aún

| Scope | Evidencia de uso | Disposición |
| --- | --- | --- |
| `read_products` | `shopify_sync.py`: catálogo | Mantener, validar feature |
| `read_inventory` | `shopify_sync.py`: `inventoryQuantity` | Mantener provisionalmente |
| `read_customers` | Sin consulta directa demostrada en el inventario parcial | **Candidato a retirar**, previa búsqueda completa y E2E |
| `read_orders` | `shopify_fulfillment.py`: `order(id)` | Mantener si fulfillment habilitado |
| `write_orders` | `shopify_cod_orders.py`: `orderCreate` | Condicional a función COD revisada |
| `write_draft_orders` | `shopify_orders.py`: `draftOrderCreate` | Condicional a función borradores revisada |
| `read_merchant_managed_fulfillment_orders` | `shopify_fulfillment.py`: `fulfillmentOrders` | Mantener si se publica fulfillment |
| `write_merchant_managed_fulfillment_orders` | `shopify_fulfillment.py`: `fulfillmentCreate` | Mantener solo si esta mutación es imprescindible |

Separar permisos opcionales de los indispensables solo después de verificar compatibilidad con instalaciones existentes y el flujo de concesión dinámico.

## Acciones de cierre y evidencia exigida

- [x] Auditoría inicial de ocho scopes y matriz de campos: referenciar `docs/shopify-p0-initial-data-inventory-2026-10-20.md` y la presente nota.
- [x] Guardar errores GraphQL sin propagar mensajes del proveedor ni aceptar resultados parciales cuando hay errores.
- [x] Preparar pruebas unitarias para GraphQL HTTP 200 con error de PCD, scope denegado, error genérico y consulta válida.
- [ ] **Ejecutar y registrar** tests en CI y en checkout local; verificar las cinco rutas afectadas con los consumidores reales.
- [ ] Completar trazabilidad campo → origen → función → tabla/columna → destino externo → retención → borrado, incluidos mensajes y analítica.
- [ ] Auditar en AWS cifrado TLS, volumen/BD, backups, S3/KMS; IAM/RBAC, MFA, accesos internos, logs de consulta sin PII, segregación de entornos y rotación de secretos.
- [ ] Revisar frontend: ante HTTP 403 con `SHOPIFY_SCOPE_DENIED` o `SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED`, explicar la acción al comerciante y deshabilitar solo la función afectada sin asumir permiso por HTTP 200.
- [ ] Reconciliar Partner Dashboard **App → API access requests → Protected customer data access** con versión activa, scope real y los cuatro campos por separado. Completar Data protection details con evidencia verídica.
- [ ] Probar tienda de desarrollo sin datos de clientes reales: acceso completo y parcial, campos `null`, scopes insuficientes, cambio de scopes, reautorización, revocación, reinstalación, roles staff y aislamiento entre dos tiendas.
- [ ] Actualizar política de privacidad y ficha Shopify solo con tratamiento comprobado y procesos que realmente operen.
- [ ] Registrar capturas saneadas, Shopify app/version, commit, resultados, aprobador y fecha; solicitar revisión final cuando no existan huecos P0.

### Matriz de prueba con tienda de desarrollo

| Escenario | Resultado esperado |
| --- | --- |
| Consulta sin error | Se devuelven únicamente los campos autorizados |
| HTTP 200 + campo PCD redactado y `errors` | No se procesa `data` parcial; error seguro `SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED` |
| HTTP 200 + `ACCESS_DENIED` | Error seguro `SHOPIFY_SCOPE_DENIED` |
| Token 401 | Se conserva error de autorización; reautorización según flujo de instalación |
| Comercio A y B con mismo email/teléfono | Un comerciante nunca recibe datos del otro; no eliminar datos compartidos sin analizar procedencia |
| Scopes revocados / permiso staff insuficiente | No se obtiene información prohibida ni se cambia el estado de otras tiendas |
| Desinstalación y reinstalación | Vínculos, credenciales y preferencias son consistentes; solicitudes de privacidad siguen su ciclo |

## Límite del presente cambio

No se han cambiado `shopify.app.toml`, permisos activos, datos de producción, respuestas de privacidad ni declaraciones de Partner. Este PR no prueba cifrado de infraestructura, aprobación de Shopify ni cierre de privacidad/exportación/borrado. El release sigue **NO-GO**.

**Fuentes oficiales:**
- https://shopify.dev/docs/apps/launch/protected-customer-data
- https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
