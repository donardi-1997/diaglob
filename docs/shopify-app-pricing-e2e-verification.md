# DIAGLOB — Shopify App Pricing: evidencias E2E para App Store

**Estado:** pendiente de validación manual en Partner Dashboard y tienda de desarrollo. La suite automatizada prueba las decisiones del backend con respuestas simuladas; **no certifica** que Shopify haya aprobado una suscripción ni una factura real.

## Configuración antes de probar

- [ ] Confirmar en **Shopify Partner Dashboard → App distribution → App Store listing → Pricing** que la app DIAGLOB usa **Shopify App Pricing**, que los planes publicados y sus importes coinciden con el catálogo aprobado, y que el enlace de bienvenida es correcto.
- [ ] Confirmar que **Starter / Growth / Pro** estén disponibles con periodos mensual y anual y el trial pactado de **3 días**. No publicar Scale en la App Store sin un cambio expreso de catálogo.
- [ ] Elegir una tienda de desarrollo de **la misma organización Partner** que DIAGLOB. No usar una tienda real para simular un cobro de prueba. Shopify documenta que la selección de planes de pago en este contexto puede probarse sin cargos.
- [ ] Revisar de forma segura y sin registrar secretos: `SHOPIFY_PARTNER_ORG_ID`, `SHOPIFY_PARTNER_APP_GID`, `SHOPIFY_PARTNER_ACCESS_TOKEN`, `SHOPIFY_APP_STORE_HANDLE` y `SHOPIFY_APP_PRICING_HANDLES_JSON`. Este último debe contener handles e importes USD de los planes **reales en Partner**, no valores inventados ni IDs Paddle.
- [ ] Comprobar el canal de la organización instalada: `billing_provider=shopify`, sin IDs heredados de Paddle. Mantener desactivado `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED` hasta contar con evidencias positivas de las pruebas de pago/recuperación.
- [ ] Usar una cuenta con permisos merchant de administrador y con sesión verificada de Shopify. Nunca introducir tokens en capturas, incidencias ni logs.

## 1.2.1 — Shopify es el único cobrador de comerciantes instalados por App Store

- [ ] Abrir DIAGLOB desde Shopify Admin tras una instalación administrada y confirmar que la pantalla de selección usa la URL de Shopify `https://admin.shopify.com/store/<shop_handle>/charges/<app_handle>/pricing_plans`, generada desde la instalación autenticada.
- [ ] Comprobar que los endpoints de checkout, upgrades y portal Paddle responden con bloqueo para una organización cuyo origen es `shopify_install` o `billing_provider=shopify`.
- [ ] Confirmar que una organización de alta directa, sin procedencia Shopify App Store, sigue usando Paddle sin afectar los comerciantes Shopify.
- [ ] Comprobar en el historial de Shopify que la suscripción pertenece a la app correcta. Ninguna cuenta de prueba debe recibir cargos Paddle.

## 1.2.2 — Aceptación, rechazo, reintento y suscripción vigente

- [ ] Con una tienda sin suscripción, abrir la página alojada; **no conceder entitlements** mientras la Partner API devuelve ausencia de suscripción.
- [ ] Seleccionar Starter mensual y **aprobar** el plan. Volver al enlace de bienvenida y comprobar que el `plan_handle` recibido es tratado solo como navegación: el backend debe consultar de nuevo `activeSubscription` en Partner API antes de proponer la activación.
- [ ] Probar rechazo/cancelación en la página alojada: volver a DIAGLOB sin acceso de pago nuevo, sin registrar el rechazo como aprobación y sin crear un cobro Paddle.
- [ ] Reintentar y aprobar; comprobar que aparece el contrato correcto (handle, precio USD, intervalo, GID de tienda), que el trial coincide con Partner y que la reconciliación no duplica cambios.
- [ ] Simular una interrupción del proveedor o una respuesta inválida; el resultado debe exigir revisión/reintento, sin habilitar acceso nuevo ni transformar un error de red en ausencia confirmada de contrato.
- [ ] Comprobar la continuidad al recargar/volver a entrar, y repetir desde una sesión nueva. Registrar el estado observado sin nombres, correos ni GIDs de tiendas.

## 1.2.3 — Cambio de plan y periodo sin reinstalar

- [ ] Con Starter activo, abrir la misma página alojada y aprobar **Growth**. Verificar que la Partner API informa el plan activo esperado y que el backend exige una revisión vinculada a la tienda y el contrato antes de aplicar entitlements.
- [ ] Cambiar **mensual ↔ anual**; verificar el monto y la periodicidad efectivas desde Partner, no desde el parámetro de redirección.
- [ ] Probar un **downgrade** (Growth → Starter) y comprobar su fecha de efectividad; si Shopify comunica `pendingUpdate`, mantener el plan **actualmente activo** hasta que el nuevo plan sea efectivo.
- [ ] Rechazar un upgrade/downgrade e intentar reabrir DIAGLOB. La suscripción anterior debe permanecer intacta.
- [ ] Probar cancelación al final del ciclo, suspensión y expiración. Verificar que una consulta posterior a Partner refleja el estado y que no existe acceso de pago no autorizado.
- [ ] Reinstalar la aplicación y confirmar que no se crea un duplicado de suscripción ni se genera un cargo externo.

## Evidencias mínimas para cerrar los tres criterios

Registrar por caso **fecha UTC, tienda de prueba anonimizada, plan anterior, acción, plan/periodo posterior observados en Shopify, respuesta funcional, referencia al workflow/commit y resultado PASS/FAIL**. Conservar capturas del flujo alojado y del historial de facturación en un repositorio privado, sin credenciales ni datos personales.

**Criterio de salida:** no marcar 1.2.1, 1.2.2 o 1.2.3 como completado con solo pruebas unitarias. Se requiere un recorrido merchant real en tienda de desarrollo y verificación de la configuración vigente de Partner, con revisión humana antes de habilitar entitlements productivos.

Referencias: https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing y https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
