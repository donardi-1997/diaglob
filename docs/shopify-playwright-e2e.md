# Shopify Playwright — pruebas de navegador de Diaglob

## Alcance

Se agregó **Playwright Test 1.65.1** en un paquete independiente (`e2e/`). La suite **mocked** ejecuta Chromium contra el **frontend React/Vite real** y sustituye exclusivamente las respuestas de `/api/**` por fixtures sintéticos.

Esto complementa —no reemplaza— `pytest` y los tests de Node. No automatiza Shopify Admin/Partner, no crea pedidos, no cobra y no efectúa borrados.

## Pruebas automáticas (PR + workflow manual)

En cada PR que modifique `e2e/**` o `frontend/**`, `.github/workflows/shopify-playwright.yml` instala la versión fija del runner, Chromium y el frontend con su lockfile. Ejecuta los escenarios, conserva reporte HTML, JUnit y trazas **solo sintéticas** cuando hay fallos, con retención de 7 días.

Escenarios cubiertos:

1. Instalación sin sesión redirige a login.
2. Un `?shop=` externo no acredita instalación.
3. Un grant OAuth vencido no se reclama.
4. La tienda verificada muestra solo tiendas compatibles; no reasigna un dominio ajeno.
5. Claim OAuth exitoso vincula solo la tienda elegida y muestra URL de Shopify Admin, sin pagos.
6. Conflicto de dominio muestra error comprensible y no confirma la vinculación.
7. Código de instalación administrada se verifica y nunca va en la URL.
8. Código administrado vencido no habilita el claim.
9. Usuario sin `stores.write` no puede reclamar la instalación.
10. Una organización facturada por Shopify no muestra checkout Paddle.
11. Enlace de planes proviene del backend verificado y solo apunta a Shopify Admin.
12. Un tenant de billing distinto bloquea la selección de planes.
13. Un onboarding Shopify aún sin conexión impide crear una suscripción.
14. El rol sin acceso a billing muestra la vista restringida.

Se inyectan tokens **ficticios**, consentimiento de cookies no publicitarias y un interceptor que aborta toda solicitud exterior a `127.0.0.1` / `localhost`. No se cargan secretos de GitHub en el job mocked.

## Uso local

```bash
npm ci --prefix frontend
npm install --prefix e2e --no-package-lock --ignore-scripts --no-audit --no-fund
cd e2e
npx playwright install chromium
npx playwright test --project=chromium-mocked
npx playwright show-report
```

Se ha fijado la versión exacta de `@playwright/test` en el paquete aislado. Este paquete no modifica `frontend/package-lock.json`; el paso de instalación indicado no escribe lockfile.

## Staging (manual, read-only, denegación por defecto)

El workflow dispone del modo **staging-readonly** solo mediante `workflow_dispatch`. Es necesario crear el environment de GitHub Actions llamado `shopify-staging`, con aprobación de revisión recomendada, y configurar:

- Variable de environment: `E2E_STAGING_BASE_URL` (HTTPS de `staging.diaglob.tech` o un subdominio de `*.staging.diaglob.tech`; **nunca** `diaglob.tech` de producción).
- Secrets del environment: `E2E_STAGING_EMAIL` y `E2E_STAGING_PASSWORD` (cuenta dedicada, Shopify billing, sin permisos de compras, borrado, facturación ni administración).

Ejecutar en GitHub Actions → `Shopify Playwright Browser E2E` → `Run workflow` → `staging-readonly`.

El navegador permite **solo** peticiones a hosts de staging y el POST necesario al endpoint Cognito para login. Bloquea todos los POST/PATCH/DELETE/PUT hacia `/api/**`, así como requests a API de producción, Paddle y Shopify. En staging **no se generan ni suben trazas, capturas ni storageState**; los secretos no se almacenan en reportes.

**Limitación:** exige que exista un deployment staging con el usuario perteneciente a una organización de pruebas con canal Shopify. Si aún no existe, el gate falla sin tocar producción. La suite comprueba la interfaz de planes y la entrada de instalación administrada, **no** entra a Shopify Admin ni modifica su App Pricing.

## Pruebas manuales aún necesarias (NO-GO independiente)

- Instalación OAuth real y reinstalación en development store de Shopify, incluidos permisos y App Bridge.
- Selección/rechazo de plan y trial en Partner con verificación de subscripción en un entorno autorizado.
- Conversación → Draft Order → checkout → order webhook, con orden de prueba y sin cobro real.
- PCD y privacidad: evidencias de consentimiento, retención, exportación/borrado en procesadores y backups.
- Meta/WABA en su propio ambiente de prueba.

**Importante:** CI verde equivale a pruebas automatizadas aprobadas, **no** aprobación de Shopify App Store ni cumplimiento legal.
