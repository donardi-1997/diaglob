# Dropi ↔ Diaglob ↔ Shopify: adaptador de integración

## Objetivo (decisión de producto)

El comerciante conserva su tienda Shopify y la conecta a Diaglob con el flujo de autorización Shopify. Además, crea una integración en Dropi y proporciona el token a Diaglob desde la interfaz protegida. Diaglob actúa como **adaptador compatible con el protocolo relevante de Dropify para WooCommerce**: no requiere una tienda WordPress/WooCommerce adicional ni una conexión directa Shopify–Dropi.

```text
Shopify (pedidos, catálogo, estados) <-- API Shopify/webhooks --> Diaglob
                                                         |
                                                   Adaptador Dropify
                                                         |
                                token Dropi / API de integraciones autorizada
                                                         |
                                                        Dropi
```

**Precisión técnica:** el plugin WooCommerce Dropify es un cliente que llama al API de integraciones de Dropi. Dropi no se conecta automáticamente a un servidor WooCommerce de Diaglob. El intermediario debe traducir órdenes y catálogos y comunicarse con ambos sistemas; **no sirve fabricar un endpoint WooCommerce y suponer que Dropi lo descubrirá**.

## Evidencia del protocolo

Código fuente público de Dropify: https://github.com/common-repository/wc-dropi-integration

- `clasess/Constants.php` define hosts de integración por país, incluido `https://api.dropi.co/integrations/`.
- `clasess/models/ProductsModel.php` usa `POST products/index`, enviando el token en `dropi-integration-key`.
- `clasess/models/OrdersModel.php` usa `POST orders/myorders` para generar pedidos, pero **el conector de Diaglob NO invoca ese endpoint**.
- El README del plugin dice que el token se obtiene al crear una tienda vinculada a un dominio WooCommerce. Esto **no prueba** que el token funcione desde el dominio o IP de Diaglob ni que esté autorizado a usarse con Shopify.

## Implementado en este PR (fase segura)

- Se admite un token separado por tienda Diaglob, cifrado usando la infraestructura de secretos existente. No se devuelve al navegador una vez guardado.
- Estado `pending_validation` hasta una prueba real; **guardar no significa conectar**.
- Solo cuando Dropi autorice el uso desde Diaglob y el operador habilite `DROPI_NATIVE_API_ENABLED=1` en el backend, se permite validar el token mediante una lectura pequeña de catálogo.
- Vista previa limitada y saneada de productos después de validación; sin datos personales de pedidos.
- Se conserva la integración de Shopify de Diaglob sin crear WooCommerce ni instalar el plugin.
- La característica está deshabilitada en producción por defecto y no genera órdenes ni realiza importaciones masivas.
- Pruebas unitarias con transporte HTTP simulado que no usan cuentas ni credenciales reales.

## Convivencia con un token independiente (modo solo lectura)

La arquitectura permite que un comerciante mantenga un token en **Dropify para Shopify** y registre **un segundo token, independiente, para Diaglob**. **La emisión y coexistencia real de dos tokens sigue sin estar validada con Dropi**. No copiar el token de Dropify a Diaglob: solicitar una nueva integración/token asociado a un dominio o identidad autorizada. No desactivar Dropify hasta terminar E2E.

- Diaglob consulta mediante `POST /integrations/products/index` (solo lectura funcional pese al verbo POST) y `GET /integrations/products/v2/{id}` (stock y variaciones).
- Se reutiliza `dropi-integration-key` solo para solicitudes autenticadas autorizadas por Dropi. No se implementan las llamadas de `orders/myorders` ni los endpoints de modificación del proveedor.
- `DROPI_NATIVE_API_ENABLED` está apagado por defecto; al habilitarlo después de autorización, **solo permite las consultas anteriores**.
- El estado de conexión anuncia `access_mode: "read_only"`, `orders_write_enabled: false` y `shopify_dropify_coexistence: "requires_independent_token_validation"`. Estos campos no constituyen verificación de que existen dos tokens activos.
- El inventario mostrado es únicamente una **lectura de referencia**. No sincroniza Shopify, no reserva existencias y no debe presentarse como garantía de disponibilidad.
- En modo convivencia **Dropify continúa siendo responsable de los pedidos** mientras no cambie la decisión operativa. Diaglob no envía pedidos, modificaciones de stock ni fulfillment a ninguna de las dos plataformas.

## Preparación de catálogo y órdenes, sin llamadas de escritura

El backend reutiliza `supplier_variant_mappings` (utilizado por CJ), con `provider=dropi`; permite gestionar correspondencias entre la variante local Shopify y los IDs de producto/variante Dropi sin afectar al proveedor CJ ni requerir una migración. No hay correspondencia automática por SKU: podría despachar un producto o talla equivocados.

Para cada orden Shopify sincronizada se ofrece un diagnóstico **de solo lectura** con controles de pago/contraentrega confirmada, estado (no cancelado/fulfill), país/datos de envío y mapeo de todas sus líneas. Los datos personales de destinatarios no salen en el diagnóstico. La clave de idempotencia es determinística por organización/tienda/ID de pedido y sirve para la futura capa de despacho; **no constituye todavía un registro de deduplicación persistente**.

La interfaz de la tienda muestra un editor de variantes y permite revisar hasta 10 órdenes recientes. La lista de mapeos muestra inicialmente las primeras 30 variantes; el backend devuelve las correspondencias completas.

**El diagnóstico no expone ni prepara un cuerpo de solicitud con datos personales**. No se ha implementado el `POST orders/myorders` en el backend Diaglob, y todo resultado tiene `can_send_to_dropi=false`.

## Bloque D: explorador del catálogo y comparación con Shopify

La ruta `GET /api/stores/{store_id}/dropi/catalog?page=1&limit=20&query=...` consulta **una sola página por petición** y devuelve solo campos autorizados: ID, nombre, SKU, tipo, existencias informadas, variaciones si están presentes en la página y los mapeos ya confirmados de Shopify.

- Parámetros acotados: página 1–1000, máximo 20 resultados por solicitud y búsqueda de hasta 100 caracteres. `startData=page`, como el plugin WooCommerce, pero el inicio de paginación se validará en pruebas reales.
- Dropi usa `no_count=true`: no se inventan totales. `has_more` solo señala que llegó una página completa, no demuestra que exista otra página.
- Las variantes incluidas en el listado se normalizan y limitan a 30; su ausencia se señala como dato desconocido, no como falta de variantes. La consulta individual de producto sigue disponible para stock/variaciones.
- La comparación cruza exclusivamente registros de `supplier_variant_mappings` para `provider=dropi` que pertenecen a la organización y tienda. **Un SKU igual no autoriza vincular ni publicar**.
- Si Dropi informó datos comparables de una variante, se señala SKU/stock igual o diferente. Si la respuesta no los incluyó, el resultado es **desconocido**; nunca se supone que hay cero stock.
- El componente `DropiCatalogExplorer` permite navegar, buscar y revisar mapeos/diferencias desde la integración validada, sin modificar Shopify ni Dropi.
- La normalización omite deliberadamente costos/precios/almacenes y datos privados hasta validar su semántica por país y token. No hay importación masiva, creación de productos, actualización de stock o escritura de pedidos.

## Antes de habilitar en producción

1. Confirmación por escrito de Dropi de que Diaglob puede utilizar un token de integración de tipo WooCommerce para integrar tiendas Shopify ajenas y de si el dominio/IP de Diaglob debe registrarse. Acordar disponibilidad, límites, webhooks y mantenimiento.
2. Validar con **token de prueba** emitido para un dominio/IP autorizado, sin pegarlo en issues, chats o logs. La captura del token debe hacerse por la UI segura de Diaglob.
3. E2E lectura de catálogo/variaciones, almacenes, stock y productos. Confirmar los campos por país y semántica de precios; revisar stock simple y variable y casos sin existencias.
4. Crear mapeo persistente Dropi product/variation ID ↔ Diaglob ↔ Shopify product/variant ID, con idempotencia y manejo de SKUs múltiples.
5. Convertir pedidos Shopify pagados/COD a orden Dropi con validación de dirección y región. **No habilitar el POST de órdenes hasta confirmar el contrato y el mecanismo de deduplicación en un entorno de prueba**.
6. Reconciliar número de guía, transportadora, estados, inventario, cancelaciones, devoluciones y errores con webhooks firmados o polling permitido. No asumir que el webhook actual de Dropi verifica una firma o modifica pedidos.
7. Cumplir las condiciones de la Shopify App Store y la autorización de acceso a tiendas; no usar credenciales privadas de otras tiendas sin consentimiento.

## Rutas

- `GET /api/stores/{store_id}/dropi`: estado sin token.
- `POST /api/stores/{store_id}/dropi/connect`: almacena token cifrado en `pending_validation`.
- `POST /api/stores/{store_id}/dropi/test`: verifica catálogo en modo autorizado y cambia estado a `verified`.
- `GET /api/stores/{store_id}/dropi/preview/products?limit=5`: lectura acotada tras verificación (1–20 artículos).
- `GET /api/stores/{store_id}/dropi/products/{product_id}`: lectura puntual de stock y variaciones con identificador de producto numérico; nunca actualiza Shopify.
- `GET /api/stores/{store_id}/dropi/catalog?page=1&limit=20&query=`: página de catálogo normalizada y comparación de productos con mapeos explícitos de Shopify.
- `GET /api/stores/{store_id}/dropi/mappings`: correspondencias Dropi por variante.
- `PUT /api/stores/{store_id}/dropi/mappings/{variant_id}`: crea/actualiza un mapeo explícito.
- `DELETE /api/stores/{store_id}/dropi/mappings/{variant_id}`: elimina el mapeo.
- `GET /api/stores/{store_id}/dropi/orders/{order_id}/readiness`: analiza elegibilidad local y faltantes, sin enviar pedidos.
- `DELETE /api/stores/{store_id}/dropi/disconnect`: elimina token.

**Fuera de alcance intencionadamente:** API WooCommerce REST, emulación de WordPress, facturación, publicación de productos Shopify, pedidos reales a Dropi, sincronización logística y E2E externo.

La conexión vía WooCommerce REST construida previamente en la rama `feat/woocommerce-dropi-bridge` es otra integración distinta, no necesaria para esta arquitectura.
