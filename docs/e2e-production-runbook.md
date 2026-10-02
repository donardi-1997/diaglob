# Diaglob — Runbook E2E de producción

Fecha de preparación: 2 de octubre de 2026.

Este documento define la prueba E2E manual de Diaglob sobre producción. El objetivo es comprobar el recorrido real del producto sin depender únicamente de tests unitarios/integración.

## 1. Regla de oro

Usar una **cuenta, organización, tienda, clientes y pedidos dedicados a E2E**.

Convención recomendada para datos temporales:

```text
E2E-YYYYMMDD-<recurso>
```

Ejemplos:

```text
E2E-20261003-Store
E2E-20261003-Customer
E2E-20261003-Automation
```

No usar clientes reales, conversaciones reales ni credenciales de terceros que no estén destinadas a pruebas.

## 2. Antes de abrir el navegador

### 2.1 Confirmar Git/CI

- `main` debe ser la rama desplegada.
- El workflow **Deploy Production** del último commit debe terminar en verde.
- No debe existir un PR pendiente que contenga un fix necesario para la prueba.
- La migración Alembic debe haberse aplicado antes del restart del API.
- El smoke post-deploy debe validar API, landing, login, registro y páginas legales.

### 2.2 Ejecutar el preflight público

Desde PowerShell 7:

```powershell
pwsh -File .\scripts\e2e-preflight.ps1 -PublicOnly
```

Debe terminar con **0 failures**.

### 2.3 Ejecutar el preflight autenticado

No guardes la contraseña en el repo. Define únicamente el correo; si no pasas contraseña, el script la solicita de forma oculta:

```powershell
$env:E2E_EMAIL = "usuario-e2e@ejemplo.com"
pwsh -File .\scripts\e2e-preflight.ps1
```

Para cuentas con múltiples organizaciones o para fijar una tienda concreta:

```powershell
$env:E2E_ORGANIZATION_ID = "123"
$env:E2E_STORE_ID = "456"
pwsh -File .\scripts\e2e-preflight.ps1
```

El preflight autenticado comprueba, sin hacer escrituras:

- Cognito login;
- `/api/me`;
- contexto de organización;
- listado de tiendas;
- Operations summary;
- Commerce summary;
- Analytics summary;
- Automation Flows;
- catálogo de herramientas autorizadas para IA.

## 3. Datos y navegador

Usar una ventana normal para el flujo principal y una ventana incógnito para pruebas de sesión/consentimiento.

Antes de iniciar:

1. DevTools > Network abierto.
2. Preserve log activado para OAuth/redirects.
3. Consola visible durante los pasos críticos.
4. Capturar screenshot únicamente cuando exista un fallo.
5. Nunca incluir tokens, cookies, contraseñas o datos sensibles en screenshots/issues.

## 4. Orden de ejecución

No empezar por integraciones complejas. Ejecutar en este orden para aislar el origen de los errores.

---

## E2E-01 — Superficies públicas y navegación

### Pasos

1. Abrir `https://diaglob.tech/`.
2. Abrir `/login`.
3. Abrir `/register`.
4. Abrir `/privacy`.
5. Abrir `/terms`.
6. Abrir `/refund-policy`.
7. Cambiar ES → EN → PT-BR en las páginas que lo soportan.
8. Cambiar dark/light.

### PASS

- No hay pantalla blanca.
- No existen errores JS bloqueantes.
- Login/registro son utilizables en desktop.
- Privacy y Terms se muestran realmente en PT-BR, no en inglés.
- Las rutas directas funcionan después de refresh.

**Severidad si falla:** P1 para login/register; P2 para legales/idioma; P3 cosmético.

---

## E2E-02 — Consentimiento de cookies y medición

Ejecutar en incógnito.

### Caso A: antes de consentir

1. Abrir landing.
2. No aceptar cookies todavía.
3. Revisar Network.

### PASS

- El banner aparece.
- La aplicación sigue siendo usable.
- No se deben cargar Meta Pixel/TikTok Pixel antes del consentimiento publicitario.
- La preferencia de cookies necesaria sí puede persistirse.

### Caso B: Solo necesarias

1. Elegir **Solo necesarias**.
2. Navegar y recargar.

### PASS

- No reaparece el banner en cada navegación.
- No salen eventos de publicidad.
- UTM/fbclid/ttclid no quedan persistidos por Diaglob para atribución publicitaria.

### Caso C: Aceptar todas

1. Abrir Cookies.
2. Activar Publicidad y medición.
3. Recargar/navegar.

### PASS

- Si los Pixel IDs están configurados, se cargan únicamente después del consentimiento.
- Si todavía no están configurados, marcar esta comprobación como **N/A**, no como fallo.

### Caso D: revocación

1. Abrir Cookies.
2. Desactivar Publicidad y medición.

### PASS

- La página se recarga.
- No se siguen iniciando nuevos eventos publicitarios.
- Se elimina la atribución local de marketing administrada por Diaglob.

---

## E2E-03 — Autenticación y sesión

### Login existente

1. Iniciar sesión con la cuenta E2E.
2. Abrir `/app`.
3. Recargar el navegador.
4. Navegar entre varias secciones.
5. Cerrar sesión.

### PASS

- El login obtiene sesión válida.
- Refresh mantiene una sesión válida.
- Logout elimina la sesión y vuelve a login.
- Una ruta `/app` sin sesión redirige a `/login`.

### Registro nuevo

Usar un correo de prueba que pueda recibir el código de Cognito.

1. Abrir Register.
2. No aceptar términos e intentar continuar.
3. Aceptar legales.
4. Completar nombre, organización, correo y password.
5. Confirmar email.
6. Entrar al workspace.

### PASS

- Sin aceptación legal no se permite registrar.
- Llega el código.
- Confirmación + provisioning crean usuario y organización exactamente una vez.
- Reintentar provisioning no duplica organización/membresía.

**Severidad si falla:** P1.

---

## E2E-04 — Organización, tienda, multi-store y RBAC

### Owner

1. Crear/usar tienda E2E.
2. Validar país, moneda, timezone e idioma.
3. Cambiar de tienda desde el selector.
4. Recargar.
5. Confirmar que el contexto permanece consistente.

### Roles

Probar al menos:

- owner;
- manager;
- operator o analyst.

### PASS

- Cada rol ve únicamente navegación permitida.
- El backend responde 403 a una acción no permitida aunque se intente fuera de UI.
- El contexto de tienda no mezcla datos entre tiendas.
- El selector multi-store no cambia el tenant organizacional por accidente.

**Severidad si hay fuga cross-store/cross-org:** P0.

---

## E2E-05 — Shopify

Usar una tienda Shopify de prueba.

### Pasos

1. Integrations → Shopify.
2. Conectar mediante OAuth.
3. Volver correctamente a Diaglob.
4. Verificar estado conectado.
5. Sincronizar productos.
6. Confirmar catálogo en Commerce.
7. Crear/usar un pedido de prueba.
8. Confirmar ingestión del webhook.
9. Repetir un webhook/pedido equivalente si es posible para validar idempotencia.
10. Probar reautorización si los scopes de fulfillment no están presentes.

### PASS

- OAuth/HMAC funcionan.
- Producto/variant correcto pertenece a la tienda correcta.
- Sync no duplica datos.
- Webhooks repetidos no regresan el estado del pedido.
- El pedido conserva IDs Shopify necesarios para fulfillment/tracking.

**Severidad:** P1; P0 si mezcla tiendas o duplica acciones financieras/logísticas.

---

## E2E-06 — CJ Dropshipping

No crear un pedido proveedor real salvo que la cuenta/flujo esté explícitamente preparado para pruebas.

### Pasos seguros

1. Conectar CJ.
2. Probar credenciales.
3. Buscar producto.
4. Consultar variantes.
5. Consultar stock.
6. Solicitar cotización de freight.
7. Mapear Shopify variant → CJ variant.
8. Refrescar la vista.

### PASS

- El mapping persiste.
- Nunca se usa una variante de otra tienda.
- Errores de proveedor se muestran sin romper la aplicación.

### Lifecycle/fulfillment

Solo con pedido E2E controlado:

1. Habilitar auto-fulfillment.
2. Confirmar que scopes Shopify necesarios existen.
3. Ejecutar lifecycle.
4. Sincronizar tracking.
5. Confirmar actualización hacia Shopify.
6. Repetir webhook de logística para validar idempotencia/retry.

### PASS

- No se duplica supplier order.
- Retry recupera estados fallidos.
- Tracking se sincroniza sin duplicar shipment.
- Webhook CJ firmado inválido es rechazado.

**Severidad:** P1; duplicación de compra/fulfillment = P0.

---

## E2E-07 — Commerce, clientes y clasificaciones

1. Abrir Commerce.
2. Buscar producto.
3. Buscar pedido.
4. Abrir Customers.
5. Buscar cliente.
6. Revisar clasificación/valor/riesgo disponibles.
7. Cambiar de tienda y repetir.

### PASS

- Búsqueda dirige al recurso correcto.
- Store identity se mantiene.
- Clasificaciones no mezclan datos entre tiendas.
- Totales y summaries coinciden con los listados usados en la prueba.

---

## E2E-08 — Knowledge

1. Crear/usar Knowledge Base E2E.
2. Agregar una fuente pequeña.
3. Sincronizarla.
4. Esperar estado de ingestión.
5. Hacer una consulta que dependa de esa fuente.
6. Eliminar/desconectar la fuente E2E al terminar.

Si se prueba Google:

- usar archivo/carpeta/Sheet de prueba;
- verificar que solo aparecen recursos autorizados;
- no usar documentos personales o sensibles.

### PASS

- Provisioning/ingestion no queda permanentemente atascado.
- Freshness/status son coherentes.
- La IA utiliza la fuente correcta.

---

## E2E-09 — WhatsApp + Conversations + IA

Usar número/conversación de prueba.

1. Conectar WhatsApp.
2. Verificar webhook.
3. Enviar mensaje inbound E2E.
4. Confirmar aparición en Conversations.
5. Confirmar store identity.
6. Generar respuesta IA.
7. Confirmar respuesta outbound.
8. Cambiar modo manual/IA si aplica.
9. Probar inbox multi-store.

### PASS

- El inbound se persiste una sola vez.
- La IA usa contexto de la tienda de esa conversación.
- No utiliza catálogo/Knowledge de otra tienda.
- La respuesta outbound llega.
- La conversación no cambia de store al usar unified inbox.

**Severidad:** P1; fuga de contexto/PII entre tiendas = P0.

---

## E2E-10 — Copiloto de operaciones

### Read-only

Preguntar, por ejemplo:

- resumen de pedidos;
- estado de operaciones;
- clientes/productos;
- tracking.

### PASS

- El LLM solo ve tools autorizadas para usuario/store.
- Las herramientas read-only pueden ejecutarse sin aprobación innecesaria.
- Las respuestas visibles corresponden a datos reales del contexto seleccionado.

### Acción con aprobación

Usar únicamente una acción E2E reversible.

### PASS

- La acción no se ejecuta antes de aprobar.
- La aprobación está ligada a usuario + store + tool + argumentos exactos.
- Reutilizar una aprobación consumida no vuelve a ejecutar la acción.
- Cancelar deja el estado intacto.

**Severidad:** ejecución no autorizada = P0.

---

## E2E-11 — Automation Flow Builder

Esta es una de las áreas prioritarias por los cambios recientes.

### Builder

1. Crear `E2E-YYYYMMDD-Automation`.
2. Agregar nodos desde palette.
3. Probar drag/drop.
4. Probar condición con ramas true/false.
5. Agregar un tool node read-only.
6. Guardar.
7. Publicar versión.
8. Activar.

### Copilot del builder

1. Pedir que agregue/modifique un flujo seguro.
2. Revisar el borrador antes de aceptar.

### PASS

- El grafo guardado es compatible con runtime.
- No permite ciclo inválido.
- Las ramas se serializan correctamente.
- Copilot no publica/activa silenciosamente.
- Solo propone tool nodes permitidos.

### Runtime + debugger

1. Ejecutar/simular el flow.
2. Abrir Runs.
3. Abrir un recipient.
4. Revisar nodos en el canvas.
5. Revisar status, duración, input/output, error y metadata.
6. Forzar un fallo controlado cuando sea posible.
7. Ejecutar **retry-from-node**.

### PASS

- Debugger usa la versión histórica del run.
- Nodo terminal muestra timestamps.
- Retry-from-node solo está disponible con `automations.write`.
- No reejecuta nodos de otra versión.
- No reejecuta recipients no terminales.
- Tool node vuelve a validar permisos en runtime.

**Severidad:** P1; bypass de permisos = P0.

---

## E2E-12 — Analytics y Operations Center

1. Abrir Dashboard.
2. Abrir Analytics.
3. Abrir Operations Center/summary.
4. Cambiar store.
5. Comparar datos con Commerce/Customers usados durante la sesión.

### PASS

- No hay health hardcodeado.
- Los indicadores reflejan la store actual.
- Un fallo de integración se muestra como degradación real, no como OK falso.
- No aparecen cifras de otra store.

---

## E2E-13 — Billing

### Pruebas seguras

- abrir planes;
- preview de upgrade/downgrade;
- verificar períodos y precios;
- cancelar una intención antes de cobro.

### Pago real

**No completar una transacción real** si Paddle está en producción y no existe una política explícita para reembolso de la prueba.

Si se cuenta con sandbox/test mode:

1. checkout;
2. webhook;
3. activación de plan;
4. upgrade prorrateado;
5. downgrade programado;
6. cancelación/auto-renew.

### PASS

- Preview y cargo coinciden.
- Upgrade no pierde el ciclo de facturación.
- Webhook repetido es idempotente.
- La organización recibe el entitlement correcto.

**Severidad:** cobro incorrecto/doble = P0.

---

## E2E-14 — Consentimiento + paid acquisition

Probar una URL con UTM:

```text
https://diaglob.tech/?utm_source=e2e&utm_medium=manual&utm_campaign=e2e_20261003&utm_content=consent_test
```

Antes de consentimiento:

- no atribución publicitaria persistida;
- no evento a Meta/TikTok.

Después de consentimiento:

- first/last touch puede persistirse;
- registro dispara los eventos previstos si Pixel ID está configurado.

Eventos relevantes:

- `landing_view`;
- `registration_started`;
- `registration_submitted`;
- `complete_registration`;
- `pricing_plan_interest`.

Los eventos de negocio posteriores `connect_shopify`, `create_automation` y `subscribe` todavía deben validarse solamente cuando estén instrumentados explícitamente.

---

## E2E-15 — Casos negativos mínimos

Probar al menos:

1. API protegida sin token → 401.
2. Organización ajena → 403.
3. Store ajena → 403/404 según contrato.
4. Rol sin write intentando acción → 403.
5. Plan/trial sin entitlement intentando write → 402.
6. OAuth/webhook con firma inválida → rechazo.
7. ID inexistente → 404, sin 500.
8. Input inválido → 4xx con mensaje controlado.
9. Refresh de navegador en rutas públicas y `/app`.
10. Dos clicks rápidos sobre acciones sensibles → sin duplicado.

## 5. Qué registrar ante un fallo

Registrar:

- ID E2E;
- hora exacta America/Bogota;
- commit desplegado;
- navegador;
- usuario/rol de prueba;
- organización/store E2E;
- pasos mínimos;
- esperado;
- actual;
- HTTP status si aplica;
- request ID/correlation data si existe;
- screenshot segura;
- si es reproducible.

No pegar:

- Authorization headers;
- cookies;
- OAuth tokens;
- API keys;
- passwords;
- payloads con PII real.

## 6. Severidad

| Nivel | Criterio |
|---|---|
| P0 | seguridad, cross-tenant, datos perdidos, cobro/compra duplicada, acción no autorizada |
| P1 | bloquea registro, login, activación, Shopify, WhatsApp, IA, automations o flujo core |
| P2 | existe workaround razonable |
| P3 | UI/copy/cosmético |

## 7. Criterio para declarar la sesión E2E aprobada

Obligatorio:

- preflight público: 0 FAIL;
- preflight autenticado: 0 FAIL;
- E2E-01, 03, 04, 05, 09, 10 y 11: PASS;
- 0 P0 abiertos;
- 0 P1 sin workaround/documentación;
- no cross-store/cross-org;
- no escrituras duplicadas;
- producción sigue healthy al terminar.

Los bloques dependientes de proveedores no configurados se marcan **N/A**, nunca PASS ficticio.

## 8. Cierre y limpieza

1. Desactivar automation E2E.
2. Eliminar datos temporales que sea seguro eliminar.
3. No eliminar evidencia necesaria para un bug abierto.
4. Desconectar integraciones E2E si no deben quedar activas.
5. Ejecutar nuevamente:

```powershell
pwsh -File .\scripts\e2e-preflight.ps1 -PublicOnly
```

6. Revisar Sentry/observabilidad por errores nuevos generados durante la sesión.
7. Clasificar hallazgos P0–P3 antes de empezar nuevos cambios.
