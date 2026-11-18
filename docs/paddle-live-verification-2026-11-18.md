# DIAGLOB — Paddle Live verification closure (2026-11-18)

## Scope

This record covers only the direct-sales Paddle integration. Shopify App Store
review credentials remain a separate path and must use Shopify App Pricing; a
Paddle subscription on the review organization can trigger the existing
`SHOPIFY_BILLING_ORGANIZATION_REQUIRED` guard during store connection.

No card data was entered and no purchase was confirmed. No real charge was made.

## Configuración verificada en Paddle Live

| Item | Estado | Evidencia |
|---|---|---|
| Cuenta | Live y verificada | El dashboard muestra “You're in Live” y “You're verified”. |
| Dominio | Aprobado | `diaglob.tech` figura **Checkout approved** y **Apple Pay approved** en Website approval. |
| Datos de payout | Guardados | El formulario de payout se conserva al recargar en una pestaña nueva. Los valores fiscales/bancarios no se reproducen aquí. |
| Catálogo | Coincide | Los ocho `pri_...` publicados coinciden con `docs/paddle-shopify-price-parity-2026-10-15.md`; Pro monthly = `pri_01m50h3z0mtsjj4vnzs5c7z164`, USD 99/mes, prueba de 3 días. |
| Webhook | Activo | `https://api.diaglob.tech/api/billing/webhook`, 11 eventos, descripción “Diaglob Production - Subscription billing and payment lifecycle webhooks”. |
| Onboarding | Configuración inicial completa | `01 Set up your live account` pasó de **In progress** a **Complete**. `02 Verify your account` está **Complete**. `03 Test and go live` sigue **In progress** porque no se realizó un pago real. |

## Causa del error “Something went wrong” y corrección

Reproducción con la cuenta aislada `shopify-review@diaglob.tech`:

1. Al pulsar **Elegir plan** en Pro, el backend devolvió correctamente
   `POST /api/billing/paddle/checkout-intent` → 200 con el price ID de Pro y
   `custom_data` firmado.
2. Paddle.js abrió `buy.paddle.com`, pero
   `POST https://checkout-service.paddle.com/transaction-checkout` terminó con
   **400**.
3. El cuerpo de la respuesta fue
   `{"errors":[{"status":400,"details":"transaction_default_checkout_url_not_set"}]}`.
4. La consola mostró
   `[PADDLE BILLING] Checkout error: transaction_default_checkout_url_not_set`.

La causa no era el price ID, el token, el entorno ni la firma: faltaba el
**Default payment link** en Paddle. Paddle exige ese enlace para crear
cualquier transacción, incluso antes de introducir una tarjeta.

Corrección aplicada en **Paddle → Checkout → Checkout settings → Default payment
link**:

```text
https://diaglob.tech/app/plans
```

Se guardó y se verificó tras recargar la página. Es una página de un dominio
aprobado que inicializa Paddle.js. `App.tsx` conserva `location.search` en
`returnTo`, de modo que un enlace de pago con `?_ptxn=...` puede volver a abrir
el checkout después de autenticar al usuario.

## Prueba final del checkout (sin pago)

Tras guardar el enlace, se recargó `/app/plans` con la cuenta de revisión y se
repitió la selección de Pro:

- El iframe `paddle_frame` cargó el checkout **Pro Monthly**.
- Se mostraron **3 días de prueba gratuita** y **99,00 US$/mes a partir del 21
  de nov de 2026**.
- Aparecieron los campos normales de tarjeta, PayPal, país e IVA/descuento.
- No apareció “Something went wrong”.
- Consola: **0 errores**.
- Red: **99 exchanges, 0 failures, 0 respuestas 4xx/5xx**.
- No se introdujeron datos de tarjeta.
- Paddle creó una transacción **Incomplete** para
  `shopify-review@diaglob.tech`, con **$0.00**, sin método de pago y sin fecha
  de pago. No hay transacciones *Completed* ni *Billed*. Abrir el overlay no
  generó ningún cargo.

## Webhook

Se republicó la simulación existente `DIAGLOB - Verificación webhook` para
`transaction.completed`:

- Destino: `https://api.diaglob.tech/api/billing/webhook`.
- Resultado: **HTTP 200**.
- Cuerpo: `{"ok":true,"ignored":true,"reason":"organization_not_found","event_type":"transaction.completed"}`.

El `ignored` es esperado porque el fixture de prueba usa un transaction ID y un
tenant que no existen en esta base; no representa un pago ni una activación de
plan. El 200 confirma transporte y firma aceptables: el handler responde **401**
cuando la firma Paddle es inválida (`backend/app/api/billing.py`). No se creó
ni se simuló una suscripción real.

## Consola: 403 en `/api/admin/overview`

Durante la navegación aparece un `403 Forbidden` en
`GET https://api.diaglob.tech/api/admin/overview`, originado en
`frontend/src/services/adminAnalytics.ts:getAdminStatus()`. No está relacionado
con Paddle ni con el checkout: `App.tsx` usa esa llamada para detectar si la
sesión es de plataforma y espera explícitamente el rechazo en `.catch()` para
marcar `isPlatformAdmin=false`. Una sesión de merchant normal produce ese 403;
no se modifica el código porque no es un fallo funcional.

## Pruebas locales

- `20 passed` para `test_paddle_direct_checkout.py`,
  `test_paddle_price_catalog.py` y `test_paddle_trialing_event.py`.
- Suite completa de backend: **3084 passed**, 20135 warnings, sin fallos.
- Build de frontend: `npm ci` instaló 215 paquetes porque `node_modules` no
  estaba presente; `npm run build` terminó correctamente (`tsc -b && vite
  build`, 2595 módulos, `✓ built in 1.44s`). Único aviso: chunks >500 kB, no
  bloqueante. `npm run lint` terminó con **0 errores** y 174 advertencias
  preexistentes (`react-hooks/*`, `no-explicit-any`), sin cambios de código.

## Registro, recuperación y Shopify E2E

Se repitió el flujo sobre una tienda de desarrollo fresca, sin usar Bakatá:

- Shopify creó la tienda `DIAGLOB Review E2E` con dominio
  `diaglob-review-e2e.myshopify.com`.
- La app se instaló desde Shopify Dev Dashboard y mostró el flujo de
  instalación gestionada.
- La cuenta de revisión se recuperó por el canal `shopify_install`; la
  organización quedó con facturación Shopify App Pricing, no Paddle.
- Se validó el código temporal de instalación, se creó la tienda local
  `DIAGLOB Review E2E` con mercado Colombia y se guardó la conexión.
- Se generó el código de vinculación de usuario y el App Home de Shopify quedó
  autenticado, mostrando el resumen de la tienda y el dominio verificado.
- No se generó ningún cargo ni se contrató un plan.
- Se probó la recuperación de contraseña usando el código recibido en el
  buzón de revisión de SpaceMail; la nueva contraseña se aceptó y el login
  posterior abrió `/app/overview` con `/api/me` autenticado.
- No apareció el error crudo `Request failed with status code 409` ni el
  bloqueo `SHOPIFY_BILLING_ORGANIZATION_REQUIRED`.

## Estado final

La configuración Live de Paddle quedó alineada con DIAGLOB y el checkout Pro
abre correctamente. Queda pendiente únicamente la prueba de pago real de
extremo a extremo que exige el paso `03 Test and go live`; esa prueba no se
hizo porque requeriría una transacción real o datos bancarios y no estaba
autorizada en esta sesión. Tampoco se activó Pro en la cuenta de revisión de
Shopify mediante Paddle; ese paso debe resolverse por Shopify App Pricing.
