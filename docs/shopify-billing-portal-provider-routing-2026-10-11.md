# Facturación visible por canal: Shopify vs. Paddle

## Motivo

La pantalla heredada `Planes y facturación` mostraba precios, checkout y controles de Paddle a todas las organizaciones. Aunque el backend protege las mutaciones de facturación Shopify, la experiencia visual era engañosa y podía invitar al usuario a intentar una compra en el proveedor incorrecto.

## Implementación

- `GET /api/organization` agrega `billing_provider` normalizado, derivado exclusivamente del registro de la organización autenticada (sin secretos). Evita consultar `PADDLE_API_KEY`/la API de Paddle salvo cuando el proveedor es realmente `paddle`, incluso si permanecen referencias heredadas en la organización.
- `BillingChannelPage` obtiene la organización antes de renderizar cualquier flujo de checkout. `paddle` muestra la pantalla de precios existente. `shopify` muestra `ShopifyBillingWorkspace`. Un canal desconocido, vacío o un error de API muestra un mensaje neutral y **ninguna acción de pago**.
- `ShopifyBillingWorkspace` permite a propietarios y administradores cargar el historial auditado de verificaciones, consultar manualmente el contrato Partner/Admin de Shopify, ver propuestas y evaluar su vigencia. Solo el rol `owner` puede preparar una propuesta de revisión.
- La UI nunca activa planes. Se verifica `applied=false` en las respuestas antes de presentarlas como exitosas. La evaluación debe informar `activation_allowed=false`, `shopify_reverified_now=false`; una propuesta clara sigue siendo solo para revisión humana.
- No hay checkout de Paddle, enlaces de pago, creación de planes, confirmación de suscripción ni mutaciones de límites de uso en la experiencia Shopify.
- Los mensajes de error se traducen a textos controlados; no se presentan los detalles arbitrarios o credenciales del proveedor. Las listas se limitan a la organización autenticada y el frontend comprueba sus identificadores como defensa adicional.
- El panel evita consultas a Shopify de forma automática: la API Partner solo se consulta al pulsar **Verificar suscripción**. La carga inicial lee únicamente el historial interno.

## Pruebas

- Backend: `test_organization.py` confirma `billing_provider`, que Shopify/unknown nunca consulta Paddle, que Paddle todavía puede consultar su próxima renovación, y que no se exponen credenciales.
- Frontend: `billingChannel.test.ts` cubre canal Shopify, Paddle, entradas desconocidas y comportamiento de bloqueo.
- Compilación TypeScript + Vite y pruebas frontend en CI. No se necesitan migraciones ni cambios de permisos de API.

## Límites conocidos

- `Organization.billing_provider = NULL` queda en estado **sin verificar**. Revisar cualquier organización heredada antes de habilitar checkout; no decidir el proveedor automáticamente basándose en que exista un token o una tienda Shopify.
- Esta pantalla no sustituye los planes aprobados en Shopify Partner ni ofrece funciones de pago. La activación de entitlements sigue explícitamente deshabilitada.
- Falta verificar la UI manualmente desde una sesión real en la tienda de desarrollo `diaglob-poc.myshopify.com` y confirmar la política multitienda. El conector Shopify actualmente vinculado a Bakatá no debe usarse para esta prueba.
- Shopify hosted pricing puede utilizar periodos distintos de las ofertas Paddle de 3/6 meses; por ello no se reutiliza en Shopify el selector heredado de periodos Paddle.

## Condición de merge

Exigir CI verde sobre el HEAD exacto, con test backend, prueba de servicio y compilación del frontend. Al fusionar, `main` inicia despliegue automático; verificar el workflow antes de informar producción actualizada.
