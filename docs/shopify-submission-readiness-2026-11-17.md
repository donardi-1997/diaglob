# DIAGLOB - Evidencia de verificación previa al envío a revisión (Shopify App Store)

**Fecha:** 2026-11-17
**Estado:** Pasos preliminares completos (`Listo para enviar`). **No se pulsó "Enviar a revisión".**
**Fuente:** sesión real de Shopify Partners (aplicación `416524435457`, listing `es`), contrastada con `main` = `1dc8dca`.

Este addendum complementa `shopify-review-closure-2026-10-27.md`, que dejaba como brecha externa la
verificación de la superficie de Partner (listing, billing y comprobaciones automáticas) por no existir
sesión en ese entorno.

## 1. Comprobaciones automáticas de errores frecuentes

La comprobación anterior había caducado (+30 días). Se ejecutó de nuevo desde
**Distribución → Revisión en Shopify App Store** y terminó en verde (~4,5 min):

- Inmediatamente autentica después de la instalación
- Inmediatamente redirige a la interfaz de la app después de la autenticación
- Proporciona webhooks de cumplimiento obligatorios
- Verifica los webhooks con firmas HMAC
- Usa un certificado TLS válido

Resultado: 9/9 pasos preliminares en verde; estado **"Listo para enviar"** y botón
`Enviar a revisión` habilitado. Comprobaciones de apps incrustadas: en verde.
Solicitud de acceso a datos de clientes protegidos (PCD): completada.

## 2. Billing - criterio 1.2.1 (Shopify App Pricing)

**Evidencia del listing (Partner):**

| Plan | Precio público | Trial |
|---|---|---|
| starter | $19/mes · $190/año | 3 días |
| growth | $49/mes · $490/año | 3 días |
| pro | $99/mes · $990/aéro | 3 días |

3 planes públicos + 2 privados; "Changes to prices and billing cycles will be updated automatically".
Checkbox **"I have approval to charge merchants outside of Shopify Billing API" = sin marcar**.

**Contraste con el código:**

- `SHOPIFY_APP_STORE_TRIAL_DAYS = 3` y `SHOPIFY_APP_STORE_PLANS = ("starter","growth","pro")` en `backend/app/services/shopify_app_pricing.py`.
- Importes `19/49/99` en `backend/app/services/admin_dashboard_service.py`.
- Cobros externos bloqueados para organizaciones conectadas con Shopify:
  `_reject_shopify_managed_billing()` (HTTP 409) en `backend/app/api/billing.py`; el endpoint de flags
  expone `paddle_checkout_available: False`.

**Conclusión:** 1.2.1 queda soportado con evidencia de Partner + código. Falta únicamente la transición
real de plan en Admin (criterio **1.2.3**), que requiere una ventana de prueba autorizada en una tienda de
desarrollo; no se ejecutó aquí.

## 3. Copy del listing - criterio 1.1.4 (información factual)

- Introducción, detalles y features verificables contra el producto (multi-store, roles, analítica,
  conversaciones) sin promesas de tiempo real ni resultados.
- Enlaces correctos: soporte `support@diaglob.tech`, privacidad `https://diaglob.tech/privacy`,
  sitio `https://diaglob.tech`.
- Screencast `https://youtu.be/6zdgFoCWVXs` accesible y público ("Diaglob Shopify Review").
- Categoría primaria: `Store management › Operations › Analytics`; capacidades: abastecimiento de
  productos e incrustada.

## 4. Hallazgos de media y corrección aplicada

Mapeo slot → imagen real → alt text:

| Slot | Imagen real | Alt text (antes) |
|---|---|---|
| Feature media | Overview en estado vacío ("Create your first store") | "overview dashboard for store operations" |
| Screenshot 1 | Overview con métricas | "analytics dashboard with operational insights" |
| Screenshot 2 | Página Stores (multi-store) | "customer conversations workspace" |
| Screenshot 3 | Página Analytics | "customer management workspace" |

**Corrección aplicada (guardada en Partner):**

- Feature media → "Diaglob overview screen for creating and setting up a new store"
- Screenshot 1 → "Diaglob overview dashboard with sales, orders, customer and conversation metrics"
- Screenshot 2 → "Diaglob multi-store operations page showing plan usage and connected stores"
- Screenshot 3 → "Diaglob analytics dashboard with revenue, orders and sales by channel"

## 5. Pendientes recomendados antes de enviar (no bloqueantes para el paso preliminar)

1. Ningún screenshot muestra **Conversaciones** ni **Clientes**, dos features anunciadas en el listing.
2. El feature media es un estado **vacío**; conviene sustituirlo por un panel con datos.
3. **Idioma mezclado** en los screenshots (UI en inglés con "Integraciones" y "Tiendas" en español).
4. Las instrucciones de prueba admiten: *"AI Agents may display a configuration error and should be
   skipped during review"*; el revisor verá una sección con error.
5. Dos cuentas de prueba con el mismo usuario (`admin@diaglob.tech`) y contraseñas distintas.
6. Campos opcionales vacíos: search terms, title tag, meta description, demo store URL y top features
   de los planes.

## 6. Acciones no ejecutadas

- No se pulsó **Enviar a revisión** (pendiente de decisión del propietario).
- No se modificaron precios, planes, capacidades ni el resto del copy.
- No se tocaron producción, tiendas ni instalaciones.
