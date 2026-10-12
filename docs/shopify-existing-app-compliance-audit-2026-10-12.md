# Shopify App Store — auditoría de configuración existente (2026-10-12)

**Estado: PENDIENTE de configuración y evidencia en el Shopify Dev Dashboard.**
Esta auditoría es de solo lectura y jamás publica una nueva versión, modifica
planes, activa facturación, concede scopes ni cambia un merchant. Su objetivo
es evitar enviar a revisión una app con webhooks de privacidad ausentes o
instalación/callback inconsistentes.

## Qué queda preparado

El backend mantiene el receptor HTTPS:

- `POST https://api.diaglob.tech/api/webhooks/shopify/compliance`
- Valida HMAC sobre cuerpo original, con límite de tamaño, antes de registrar
  el recibo cifrado en una cola. Un HMAC inválido debe devolver **HTTP 401**.
- Un recibo válido **no** demuestra exportación o borrado real: esos procesos
  siguen bloqueados por retención, proveedores externos, copias de seguridad
  y revisión legal. No presentar esta funcionalidad como cumplimiento completo.

El workflow de despliegue prueba en producción una petición **firmada
incorrectamente** y exige HTTP 401. No envía datos de clientes válidos ni
solicitudes de borrado reales.

## Auditar la aplicación *existente* (sin generar un TOML inventado)

1. Desde Shopify CLI autenticado, vincular la configuración con la app
   existente de Diaglob en Shopify Dev Dashboard. Confirmar que corresponde
   a la app ID **416524435457**, Partner **5148778**; no crear una app nueva.
2. Revisar en el Dev Dashboard los valores **reales** de `client_id`,
   `application_url`, `embedded`, versión activa, `access_scopes` y
   `auth.redirect_urls`, y guardarlos en el `shopify.app.toml` vinculado.
   El código está preparado para OAuth-first **standalone**, pero NO hay
   confirmación de que el modo del dashboard corresponda.
3. En el TOML vinculado, bajo la sección `[webhooks]` ya existente,
   registrar **exactamente una vez** la siguiente suscripción
   (no crear una segunda sección `[webhooks]`):

   ```toml
   [[webhooks.subscriptions]]
   compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
   uri = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
   ```

4. Con `SHOPIFY_CLIENT_ID` establecido localmente desde la configuración
   autorizada y el `shopify.app.toml` enlazado, ejecutar el chequeo desde
   `backend/` (Python 3.10 con `pip install -r requirements.txt`):

   ```bash
   python -m app.shopify_app_config_audit \
     --path /RUTA/REAL/shopify.app.toml \
     --expected-app-url "https://URL_REAL_DE_LA_APP_SEGUN_DASHBOARD" \
     --expected-mode standalone
   ```

   Reemplazar el URL por el **verificado** en Shopify; usar `embedded`
   únicamente si ese es el modo real. Si las URLs de callback difieren
   del `https://api.diaglob.tech/api/shopify/callback` del backend,
   detener y reconciliar; no ajustar los dominios a ciegas.

   La salida solo contiene `static_valid`, `failures` (códigos, sin
   credenciales/URLs) y `deployed_version_verified=false`.
   Salida 0 significa únicamente que el TOML local es coherente con
   los valores esperados; salida 1 significa bloqueo. Cualquier callback
   adicional exige evaluación antes de pasar esta auditoría.

5. **Sólo después de validar la app activa y con aprobación operativa**,
   publicar la configuración en la aplicación original desde Shopify CLI.
   Comprobar en Dev Dashboard que la **versión desplegada** incluye
   efectivamente las tres suscripciones y el callback correcto.
   Un archivo local conforme NO actualiza automáticamente las suscripciones.
6. Para verificar la entrega, usar el webhook de prueba de Shopify CLI
   en una tienda de desarrollo autorizada. El disparo manual no demuestra
   por sí mismo que la suscripción exista. Comprobar HMAC, entrega y
   persistencia, sin activar redacciones de datos reales.
7. Revisar con el responsable legal el inventario de datos, plazos,
   retención y copias de seguridad antes de procesar solicitudes reales.
   Shopify exige responder a las solicitudes de datos y redacción en sus
   condiciones aplicables; **la cola recibidora sola no cierra ese requisito**.

## Bloqueos de publicación que permanecen

- App Store: categoría, medios/capturas, correos, instrucciones y cuenta de revisión.
- OAuth-first: `SHOPIFY_OAUTH_FIRST_ENABLED=false` hasta comprobar el modo
  real del dashboard y probar instalación/reinstalación en
  `diaglob-poc.myshopify.com` con OAuth anterior a cualquier UI.
- Billing: App Pricing de Shopify sin plan/handles de prueba confirmados;
  no activar beneficios comerciales ni permitir cobros de prueba reales.
- Privacidad: procesamiento completo, retención/legal holds, backups,
  datos derivados, proveedores externos y prueba E2E de derechos.

## Fuentes Shopify

- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/build/webhooks/subscribe
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
