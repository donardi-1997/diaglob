# DIAGLOB — Shopify: decisión B2 de minimización de scopes (2026-10-20)

**Estado:** cambio propuesto exclusivamente en source. **No desplegado** en Shopify App ni en producción. La configuración declarada y la constante de OAuth se reducen de ocho a **siete** scopes al excluir `read_customers`.

## Fundamento de la reducción

- `backend/app/shopify_sync.py` consulta productos, variantes e inventario, no el objeto Customer de Shopify.
- `backend/app/services/shopify_fulfillment.py` consulta órdenes y fulfillment, sin búsqueda directa de clientes.
- `backend/app/services/shopify_webhook_service.py` **sí recibe** identificador, nombres, correos, teléfonos y direcciones de compradores de webhooks de pedidos. Esto **sigue siendo tratamiento de Protected Customer Data (PCD)** incluso después de retirar `read_customers`.
- `backend/app/shopify_cod_orders.py` y `backend/app/shopify_orders.py` transmiten datos facilitados a DIAGLOB para crear pedidos/borradores; no constituyen evidencia independiente de que se necesite el scope de lectura directa de `Customer`.
- El guard de fuente `backend/tests/test_shopify_minimum_customer_scope.py` rechaza consultas literales directas `customer(...)` y `customers(...)` en módulos que referencian `ShopifyGraphQLClient`; **no verifica expresiones dinámicas, tokens activos ni proveedores externos**.
- Documentación oficial de Shopify: scopes de pedidos, drafts, fulfillment y webhooks también pueden involucrar información de clientes. No basta retirar `read_customers` para declarar que no se requiere PCD.

## Scopes propuestos — siete requeridos

| Scope | Motivo funcional | Revisión posterior |
| --- | --- | --- |
| `read_products` | Catálogo y variantes | Conservar |
| `read_inventory` | Cantidad/disponibilidad | Comprobar recursos exactos |
| `read_orders` | Estado y seguimiento | Comprobar posible redundancia con `write_orders` y 60 días |
| `write_orders` | Flujo COD `orderCreate` | Revisar cumplimiento checkout y necesidad en ficha pública |
| `write_draft_orders` | `draftOrderCreate` | Evaluar grants opcionales tras UX de consentimiento |
| `read_merchant_managed_fulfillment_orders` | Fulfillment y líneas | Revisar dependencia real de read + write |
| `write_merchant_managed_fulfillment_orders` | `fulfillmentCreate` | Evaluar permiso opcional solo si hay solicitud dinámica implementada |

**Scope excluido:** `read_customers` — no existe necesidad directa demostrada en los flujos de API Shopify inspeccionados. La reducción propuesta deberá revertirse o ajustarse si las pruebas funcionales muestran una dependencia legítima.

## Precauciones antes del despliegue

1. Confirmar permisos de la **versión activa** y de una tienda de desarrollo. El archivo local TOML no despliega scopes ni actualiza las instalaciones hasta liberar una versión Shopify.
2. Registrar el estado actual de `currentAppInstallation { accessScopes { handle } }` y comparar antes/después usando credenciales aprobadas sin imprimir tokens.
3. Verificar el mismo token en instalación administrada, refresh, OAuth, webhook, productos, pedidos y fulfillment. Prueba de comercio sin `read_customers`; probar reautorización y reinstalación.
4. La aplicación solo debe declarar PCD nivel 1/2 y los campos nivel 2 indispensables (**nombre, correo, teléfono, dirección**), cada uno justificado y sujeto a autorización Shopify.
5. Eliminar una scope de lectura de Customer no equivale a purgar datos persistidos. Mantener bloqueos de privacidad y retención hasta prueba completa de exportación/borrado.
6. Conservar `read_orders` y ambos scopes merchant-managed de fulfillment en este cambio: aunque los permisos `write_` puedan implicar lectura según la documentación, el código comprueba grants explícitos de fulfillment y la matriz funcional todavía necesita QA. No reducir por intuición.
7. No habilitar optional scopes sin UI de solicitud/denegación, soporte de revocación y validación de comportamiento con grants parciales.
8. No desplegar cambios en Shopify ni retirar aprobaciones de clientes actuales hasta que CI, tienda de desarrollo, Partner Dashboard y responsable del producto autoricen la transición.

## Evidencias de cierre

- [x] Cambio source `shopify.app.toml` y `backend/app/shopify_oauth.py` alineado.
- [x] Pruebas añadidas para coherencia de OAuth/TOML y guard de consulta directa Customer.
- [ ] CI verde del PR en SHA final.
- [ ] Lectura y captura saneada de scopes efectivos en Shopify Dev Dashboard / tienda de desarrollo.
- [ ] Pruebas con Shopify GraphQL, órdenes, fulfillment, webhook y reinstalación.
- [ ] Reconciliar los campos de PCD nivel 2 declarados en Partner con el consumo real.
- [ ] Aprobar y desplegar versión solo tras revisión; verificar acceso tras reducción.
- [ ] Corregir política de privacidad y documentación pública; preservar el bloqueo P0 de borrado/exportación real si sigue abierto.

**Resultado esperado:** reducir acceso directo al recurso Customer sin romper funciones comerciales ni ocultar que DIAGLOB maneja datos personales de pedidos.

Referencias:
- https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes
- https://shopify.dev/docs/apps/launch/protected-customer-data
- https://shopify.dev/docs/api/usage/access-scopes
