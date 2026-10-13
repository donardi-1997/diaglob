# Diaglob → WooCommerce → Dropify → Dropi (fase 1)

## Decisión técnica (12 octubre 2026)

Dropi documenta que su **token WooCommerce** se genera en Dropi y se
introduce en **Dropify → Configuraciones** dentro de WordPress. Es un
token para el plugin Dropify, **no un token REST estándar de WooCommerce
ni una garantía de acceso a una API pública de Dropi**.

Se ha implementado un puente de consulta **solo lectura** mediante la
API oficial de WooCommerce v3. No se simulan APIs, pedidos o inventario
de Dropi.

### Responsabilidades

1. El comercio (WordPress + WooCommerce) recibe productos y pedidos.
2. Dropify gestiona su vínculo con Dropi mediante el token creado en Dropi.
3. Diaglob usa una pareja REST *Consumer Key / Consumer Secret*
   independiente de WooCommerce para verificar la tienda y leer datos.
4. Diaglob **no** crea pedidos en Dropi ni modifica pedidos WooCommerce
   con esta versión: el flujo extremo a extremo requiere validación.

## Requisitos

- Sitio WordPress + WooCommerce, públicamente accesible por HTTPS/443,
  con rutas REST configuradas (enlaces permanentes no «simples»).
- Plugin **Dropify (wc-dropi-integration)** compatible instalado y activado.
- En Dropi, integración WooCommerce creada; token pegado en configuración
  de Dropify, no en Diaglob.
- En WooCommerce → Ajustes → Avanzado → API REST, generar un par
  **Consumer Key / Consumer Secret** para Diaglob. Para este MVP de
  lectura, usar permisos **Read**; la autorización deberá ampliarse solo
  si luego se implementa un flujo de escritura validado.
- En el backend, configurar `DROPPI_TOKEN_ENCRYPTION_KEY` como clave
  Fernet existente de Diaglob; no debe aparecer en Git ni en logs.
  En una fase siguiente conviene migrar a una clave dedicada WooCommerce.
- Usuario Diaglob autorizado para gestionar la tienda.

## Flujo para conectar

1. Crear o abrir la tienda de Diaglob con la misma organización.
2. Abrir Integraciones → WooCommerce + Dropi.
3. Introducir URL HTTPS de WooCommerce, Consumer Key y Consumer Secret.
4. Diaglob valida `GET /wp-json/wc/v3/products?per_page=1`,
   sin operaciones de escritura. Si falla, no almacena credenciales.
5. Diaglob cifra las claves en `CommerceConnection` del comercio
   (`provider=woocommerce`) y activa prueba si corresponde conforme al
   mecanismo actual de identidad de la plataforma.
6. En la tarjeta, consultar productos/pedidos para comprobar que la
   tienda WooCommerce entrega resultados.
7. Verificar manualmente en Dropify y Dropi un producto importado, un
   pedido de prueba y su estado en Dropi. Hasta entonces la etiqueta
   **Dropi sin verificar** es intencional.

## Endpoints

Todos requieren JWT de Diaglob, pertenencia a organización, permisos
y visibilidad de tienda. No se expone el token Dropi.

| Verbo | Ruta | Efecto |
|---|---|---|
| GET | `/api/stores/{id}/woocommerce` | Estado sin secretos |
| POST | `/api/stores/{id}/woocommerce/connect` | Verifica y cifra claves WooCommerce |
| POST | `/api/stores/{id}/woocommerce/test` | Prueba REST sin escritura |
| GET | `/api/stores/{id}/woocommerce/preview/products` | Máximo 20 productos |
| GET | `/api/stores/{id}/woocommerce/preview/orders` | Máximo 20 pedidos con PII excluida |
| DELETE | `/api/stores/{id}/woocommerce/disconnect` | Revoca **en Diaglob** claves locales, no en WordPress |

Ejemplo de payload de `connect` (valores ficticios):

```json
{
  "site_url": "https://tienda.example.com",
  "consumer_key": "ck_example",
  "consumer_secret": "cs_example"
}
```

## Alcance y riesgos pendientes

- La API WooCommerce confirma **WooCommerce**, no autenticidad ni estado
  de la conexión interna **Dropify ↔ Dropi**; la verificación de ese tramo
  exige tienda real y una orden de prueba observada en ambos extremos.
- No hay por ahora importación a tablas internas de productos/pedidos,
  webhooks de WooCommerce, escritura de pedidos ni actualizaciones
  automáticas de tracking o stock. Los controles `preview` **no son
  sincronización**.
- No usar simultáneamente un flujo automatizado que cree un pedido en
  WooCommerce y otro que cree directamente el mismo pedido en Dropi.
  Debe existir un solo dueño del despacho e idempotencia por orden.
- Antes de automatizar, definir mapeo de producto/variación SKU, moneda,
  COD, tasas y dirección, estados, idempotencia, cancelación, reintentos,
  polling de reconciliación y marcadores de proveedor.
- Se valida URL HTTPS, puerto 443, DNS público en cada petición y se
  bloquean redirecciones. Es **obligatorio** reforzar con reglas de egress
  de red que bloqueen IP internas para neutralizar el riesgo residual
  de DNS rebinding al permitir dominios suministrados por comerciantes.
- La API puede no funcionar si un proxy elimina la cabecera Authorization,
  si la tienda no publica REST v3 o si WordPress fuerza redirecciones;
  corregir configuración del comercio, **no** poner secretos en la URL.
- No se han probado pedidos reales ni acceso a una tienda WooCommerce
  del usuario. No considerar listo para producción hasta E2E y revisión CI.

## Próximo corte

1. Levantar/identificar tienda WooCommerce de prueba y activar Dropify.
2. Obtener el token WooCommerce **desde Dropi** y configurarlo en Dropify.
3. Conectar WooCommerce a Diaglob con las claves REST de solo lectura.
4. Verificar productos, variaciones, stock y una compra COD de extremo
   a extremo; registrar IDs de Woo y Dropi, sin almacenar PII de prueba.
5. Diseñar persistencia idempotente, webhooks Woo HMAC-SHA256 y
   conciliación periódica; solo después habilitar escritura automática.

## Referencias

- Dropi: https://dropi.co/integraciones
- Plugin Dropify: https://wordpress.org/plugins/wc-dropi-integration/
- API WooCommerce: https://developer.woocommerce.com/docs/apis/rest-api/
- Autenticación REST: https://developer.woocommerce.com/docs/apis/rest-api/authentication
- Webhooks HMAC: https://developer.woocommerce.com/docs/apis/rest-api/v3/webhooks/
