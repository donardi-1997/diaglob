# DIAGLOB: actualización controlada de los scopes Shopify — ejecución

**Fecha:** 2026-10-20. **Objetivo:** actualizar la configuración de la aplicación **existente DIAGLOB** en Shopify, sin crear otra app ni activar exportación/borrado de datos reales. **Estado:** preparación de un flujo manual para crear una versión **SIN LIBERAR**. La ejecución de este procedimiento no demuestra acceso a PCD, instalación E2E ni autorización de publicación App Store.

## Identidad de la aplicación

- Aplicación Shopify **DIAGLOB**, app GID comprobado históricamente: gid://shopify/App/416524435457.
- Client ID público exacto: c5fc9aed710462d41767477fa9e595c0.
- App Home: https://api.diaglob.tech/api/shopify/embedded.
- Tienda de pruebas: diaglob-poc.myshopify.com, plan Basic App Development. La verificación read-only previa confirma app instalada en esa tienda; **no** da control de versiones de Partner.
- Arquitectura seleccionada: **Shopify-managed installation con token exchange / App Bridge**, no forzar OAuth legacy.
- Documento de evidencia viva anterior: docs/shopify-diaglob-poc-live-scope-audit-2026-10-20.md.

### Baseline observado de la tienda POC el 20-Oct-2026

| Conjunto | Lista |
| --- | --- |
| Código fuente, Shopify TOML y backend OAuth (7) | read_products, read_inventory, read_orders, write_orders, write_draft_orders, read_merchant_managed_fulfillment_orders, write_merchant_managed_fulfillment_orders |
| Shopify requested (6) | read_customers, read_inventory, read_orders, read_products, write_orders, write_products |
| Shopify granted (6) | read_customers, read_inventory, read_orders, read_products, write_orders, write_products |
| Faltantes en requested/granted | write_draft_orders, read_merchant_managed_fulfillment_orders, write_merchant_managed_fulfillment_orders |
| Sobran en requested/granted | read_customers, write_products |
| Shopify PCD Nivel 1/2 | **NO VERIFICADO** |

Estos resultados provienen de una consulta de solo lectura a la tienda POC sobre la app DIAGLOB por su Client ID público. No son una inspección de Partner ni certifican la versión activa.

## Primer paso: crear solo una versión SIN liberarla

Está preparado el workflow **Stage existing DIAGLOB Shopify version (manual only)** en GitHub Actions. No se ejecuta en pushes, merges, cron ni PR. Requiere:

1. Generar **App Automation Token** en **Shopify Dev Dashboard → Apps → DIAGLOB → Settings → App Automation Token**. Debe pertenecer a la app DIAGLOB existente; **no** al API token Admin de un comercio, ni a una app creada accidentalmente.
2. Guardarlo como secreto GitHub Actions a nivel del repositorio llamado exactamente **SHOPIFY_APP_AUTOMATION_TOKEN**. No copiar el token en issues, documentación, variables públicas, comentarios ni logs.
3. Antes de ejecutar, comprobar en Dev Dashboard que la app exacta (client ID de arriba) existe, si la versión vigente contiene extensiones, reglas de instalación/billing y si las opciones PCD de Shopify están justificadas. Un app version creada usando CLI solo incluye las extensiones presentes localmente. Si faltan extensiones en este repo, NO liberar una versión CLI que pudiera retirarlas. En caso de duda, preparar la versión en Dev Dashboard conservando extensiones.
4. Ejecutar manualmente el workflow **únicamente desde main**, introduciendo la confirmación literal **STAGE-DIAGLOB-NO-RELEASE**.
5. El job comprueba identidad, 7 scopes exactos, ausencia de permisos heredados, URL embedded, callback, GDPR webhooks y bloquea cambios adicionales de configuración local. Solo después instala Shopify CLI y ejecuta **shopify app deploy --no-release --no-input**, adjuntando commit origen. Si falta el token o el linkage a la app, falla en cerrado. No vincular de forma interactiva el repositorio a otra aplicación.
6. Registrar el nombre de versión **creada, no liberada**. Comprobar sus cambios (incluyendo extensiones, scopes, compliance webhooks y URLs) contra la versión activa en Dev Dashboard. No presionar **Release** sin revisar el impacto sobre TODAS las tiendas instaladas.
7. Solo después de validar ese diff y contar con autorización operativa para el cambio de producción, liberar la versión exacta desde Dev Dashboard o **shopify app release --version=VERSION**. Shopify actualiza la versión para **todas** las tiendas instaladas. Esto puede exigir consentimiento del merchant para scopes añadidos.
8. Abrir DIAGLOB desde Shopify Admin en la POC, atender la solicitud de autorización, y repetir **appByKey requestedAccessScopes + installation.accessScopes**, o ejecutar **python -m tools.shopify_dev_store_scope_gate** desde backend usando credenciales de tienda introducidas **solo en un entorno secreto**. Confirmar siete scopes correctos en ambas listas y eliminación de read_customers/write_products.

**El workflow únicamente implementa pasos 4–5.** Los pasos 1–3 y 6–8 necesitan comprobación y aprobación de un operador real; no están automatizados ni realizados por este cambio.

## Guía alternativa con Shopify CLI interactivo

Si no se usa GitHub Actions, un operador autenticado puede hacerlo localmente desde la raíz del repo. Confirmar primero el linkage de la aplicación existente y sus extensiones; **no ejecutar Shopify app init/create**:

    python backend/tools/shopify_scope_release_preflight.py
    shopify app versions list
    shopify app deploy --no-release

El CLI puede exigir un proyecto Shopify válido, autenticación o un archivo de configuración vinculado. Ante cualquier prompt para crear app o reemplazar extensiones, detenerse y revisar el vínculo con la aplicación existente.

## Puertas de lanzamiento que siguen abiertas

- [x] PRs de reducción de scopes y gate read-only fusionados en main; pruebas sintéticas exitosas.
- [x] Shopify POC está instalada y el drift se comprobó con metadatos reales (sin leer datos personales).
- [x] Preflight de staging offline y workflow manual **sin release** preparados en PR.
- [ ] Comprobar el App Automation Token y generar efectivamente una versión **no liberada**.
- [ ] Revisar diff de versión y extensiones en la app DIAGLOB existente.
- [ ] Autorizar publicación global de nueva versión Shopify sin afectar otros clientes.
- [ ] Abrir app en POC, aprobar scopes añadidos y comprobar grants actualizados.
- [ ] Verificar las 3 privacy webhook subscriptions en la versión activa y entregas reales firmadas.
- [ ] Completar declaraciones PCD por campos y acceso de compradores en Shopify Dev Dashboard, separar permiso por scope de aprobación PCD.
- [ ] E2E instalar/reautorizar/reinstalar, aislar tiendas, roles, compra/fulfillment con datos sintéticos, y validación de privacidad.
- [ ] No marcar Shopify App Store GO hasta evidencias externas y datos protegidos completos.

Fuentes oficiales:
- https://shopify.dev/docs/apps/launch/deployment/deploy-app-versions
- https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes
- https://shopify.dev/docs/apps/build/dev-dashboard/app-automation-tokens
- https://shopify.dev/docs/apps/launch/deployment/deploy-in-ci-cd-pipeline

**NOTA:** El pipeline habitual de GitHub **Deploy Production** publica el backend de DIAGLOB, no la versión de configuración de Shopify. No inferir cambios de scopes remotos al hacer merge de este PR.
