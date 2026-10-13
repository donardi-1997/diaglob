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

## Antes de habilitar en producción

1. Confirmación por escrito de Dropi de que Diaglob puede utilizar un token de integración de tipo WooCommerce para integrar tiendas Shopify ajenas y de si el dominio/IP de Diaglob debe registrarse. Acordar disponibilidad, límites, webhooks y mantenimiento.
2. Validar con **token de prueba** emitido para un dominio/IP autorizado, sin pegarlo en issues, chats o logs. La captura del token debe hacerse por la UI segura de Diaglob.
3. E2E lectura de catálogo/variaciones, almacenes, stock y productos. Confirmar los campos por país y semántica de precios.
4. Crear mapeo persistente Dropi product/variation ID ↔ Diaglob ↔ Shopify product/variant ID, con idempotencia y manejo de SKUs múltiples.
5. Convertir pedidos Shopify pagados/COD a orden Dropi con validación de dirección y región. **No habilitar el POST de órdenes hasta confirmar el contrato y el mecanismo de deduplicación en un entorno de prueba**.
6. Reconciliar número de guía, transportadora, estados, inventario, cancelaciones, devoluciones y errores con webhooks firmados o polling permitido. No asumir que el webhook actual de Dropi verifica una firma o modifica pedidos.
7. Cumplir las condiciones de la Shopify App Store y la autorización de acceso a tiendas; no usar credenciales privadas de otras tiendas sin consentimiento.

## Rutas

- `GET /api/stores/{store_id}/dropi`: estado sin token.
- `POST /api/stores/{store_id}/dropi/connect`: almacena token cifrado en `pending_validation`.
- `POST /api/stores/{store_id}/dropi/test`: verifica catálogo en modo autorizado y cambia estado a `verified`.
- `GET /api/stores/{store_id}/dropi/preview/products?limit=5`: lectura acotada tras verificación.
- `DELETE /api/stores/{store_id}/dropi/disconnect`: elimina token.

**Fuera de alcance intencionadamente:** API WooCommerce REST, emulación de WordPress, facturación, publicación de productos Shopify, pedidos reales a Dropi, sincronización logística y E2E externo.

La conexión vía WooCommerce REST construida previamente en la rama `feat/woocommerce-dropi-bridge` es otra integración distinta, no necesaria para esta arquitectura.
