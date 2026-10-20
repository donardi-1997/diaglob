# DIAGLOB — Corrección controlada de declaraciones de Shopify Partner PCD

**Fecha:** 2026-10-20 · **Aplicación:** DIAGLOB pública existente (Shopify Partner app ID `416524435457`) · **Estado real:** solicitud `Borrador`, no aprobada. **No se modificó el formulario de Shopify Partner mediante este expediente.**

**Normativa:** https://shopify.dev/docs/apps/launch/protected-customer-data?locale=es

La información procede de capturas del propietario de **Protected customer data access** y **Data protection details** y auditoría parcial en repo. Las 16 respuestas respondidas en Shopify no son 16 controles acreditados. Solo el propietario debe guardar respuestas en Partner; no enviarlas a revisión hasta la firma de seguridad/privacidad y verificación de producción.

## A. Sección 1 — Fines declarados y campos

| Apartado | Motivos a conservar por ahora | Cambio en Partner | Condición |
| --- | --- | --- | --- |
| Protected customer data (general) | Gestión de la tienda; Funcionalidad de la app | Mantener | Pedido y fulfillment documentados |
| Nombre | Gestión de la tienda; Funcionalidad de la app | **Desmarcar Personalización** y guardar | No hay uso de personalización probado |
| Email | Gestión de la tienda; Funcionalidad de la app | Conservar *provisionalmente* | Debe demostrarse necesidad real de comunicaciones/identidad de pedido; minimizar almacenamiento |
| Teléfono | Gestión de la tienda; Funcionalidad de la app | Conservar *provisionalmente* | Debe demostrarse uso real en coordinación de entrega; no obligatorio para todas las tiendas |
| Dirección | Gestión de la tienda; Funcionalidad de la app | Mantener si la logística física la utiliza | Necesaria para envíos físicos de comerciantes |
| Publicidad, marketing, analítica y atención al cliente | Ninguno salvo evidencia funcional y finalidad | No añadir | No confundir uso de pedidos con campañas, scoring o perfiles |

Esta es la selección de **datos solicitados**, no una aprobación Partner ni el criterio de minimización final. Pedidos y webhooks que incluyen nombre, dirección, email y teléfono implican **PCD Nivel 2**; quitar `read_customers` no elimina ese tratamiento. Shopify permite guardar selección y campos para tiendas de desarrollo sin solicitar revisión pública.

## B. Sección 2 — Declaraciones de protección (16)

**Regla de atestación:** `Sí` solamente después de validar operativamente el control y sus evidencias; `No` si no existe; `No corresponde` solamente si la condición que origina el requisito realmente no se da, con análisis documentado. Los valores de «acción» NO son cambios hechos en Partner.

| # | Pregunta resumida que aparece en Shopify | Valor en captura | Corrección / decisión fundamentada | Evidencia necesaria antes de sostener «Sí» |
| --- | --- | --- | --- | --- |
| 1 | Procesa el mínimo PII necesario | Sí | **Revisar; no dar por acreditado** | Matriz campo→función y revisión de email, teléfono, notas libres y procesadores |
| 2 | Informa al comerciante qué procesa y para qué | Sí | **Revisar** | Política y DPA publicados, accesibles y vigentes con lista de subprocesadores |
| 3 | Limita tratamiento a finalidad declarada | Sí | **Revisar** | Controles de uso secundario, segmentación de datos y pruebas de finalidad |
| 4 | Acuerdos de privacidad/protección con comerciantes | Sí | **Revisar** | DPA/contrato aceptado efectivamente; URL/versión y consentimiento de comerciante |
| 5 | Respeta decisiones de consentimiento | Sí | **Revisar aplicabilidad y ejecución** | Pruebas por uso; no suponer consentimiento para analítica/marketing |
| 6 | Respeta exclusión de venta/compartición de datos | Sí | **Evaluar «No corresponde» si se demuestra no venta/compartición regulada; si aplica, probar mecanismo** | Inventario de terceros, flujos, leyes aplicables y opt-out E2E |
| 7 | Permite excluir decisiones automáticas de efectos significativos | Sí | **Evaluar «No corresponde» SOLO si DIAGLOB no toma tales decisiones; si aplica, acreditar opt-out/manual** | Inventario de agentes y decisiones, perfilamiento/scoring, impacto sobre consumidores |
| 8 | Períodos de retención efectivos | Sí | **Pendiente, no acreditado** | Calendario aprobado, jobs, GDPR borrado/export real y copias históricas |
| 9 | Cifrado de PII en reposo y tránsito | Sí | **Pendiente evidencia integral** | TLS real, cifrado disco/DB/PostgreSQL/archivos/servicios y claves |
| 10 | Backups cifrados | Sí | **Pendiente evidencia integral** | Snapshots/DB backup cifrados, permisos, retención y restauración probada; auto snapshot ≠ prueba completa |
| 11 | Separa datos de prueba de producción | Sí | **Pendiente evidencia; alto riesgo de afirmación incorrecta** | Matriz de entornos, credenciales/BD aisladas y evidencia de ausencia de PII real en pruebas; POC Shopify usa backend prod |
| 12 | Estrategia DLP | Sí | **Pendiente** | Prevención exfiltración, clasificación PII, monitoreo/alertas y restricciones de egress |
| 13 | Limita accesos staff | Sí | **Parcial, no acreditado extremo a extremo** | Matriz IAM/staff, MFA, least privilege, revisión de autorizaciones por tienda |
| 14 | Contraseñas fuertes staff | Sí | **Pendiente de verificar** | Configuración del IdP (Cognito u otro), política de contraseñas, MFA |
| 15 | Registro de accesos a PII | Sí | **Parcial, no acreditado integralmente** | Todos los puntos de consulta/mutación, eventos sin PII, centralización, retención y revisión |
| 16 | Política de incidentes | **No** | **Mantener No por ahora** | Plan `docs/security/incident-response-plan.md` está en borrador: responsables nombrados, canal, aprobación y ejercicio; el ejercicio es buena práctica de verificación interna, no obligación textual separada de Shopify |

**Criterio operativo para guardar la sección 2 ahora:** si el propietario no dispone de evidencia real para las respuestas `Sí` con «Pendiente», debe **cambiarlas a `No`** antes de cualquier envío y planificar su implementación; en los ítems condicionales seleccionar `No corresponde` solo tras comprobación documentada. No marcar afirmaciones positivas basándose únicamente en este documento o existencia de un archivo técnico. La selección honesta puede impedir la aprobación de Nivel 2: ese es un bloqueo de cumplimiento real, no un error de formulario.

## C. Campo de auditorías/certificaciones

Las entradas actuales, según captura, son `Security hardening review — September 2026` y `Shopify integration security review — September 2026`. El campo pregunta por auditorías/certificaciones **realizadas por terceros**. No existe en el expediente evidencia de auditor externo, informe firmado o certificación. **Borrar las entradas si fueron revisiones internas**; si realmente hubo auditoría externa, conservar solo la(s) que pueda(n) respaldarse con organismo, fecha y reporte. No atribuir SOC 2/ISO por conjetura. Shopify no requiere una certificación externa universal para Nivel 2.

## D. Procedimiento de guardado manual seguro

1. Abrir `https://partners.shopify.com/5148778/apps/416524435457/api_access` → Acceso a datos de cliente protegidos → Gestionar.
2. En **Nombre**, desmarcar **Personalización**, conservar fines reales, pulsar **Guardar**. No tocar ni enviar `read_all_orders`.
3. En **Detalles de protección de datos** revisar cada una de las 16 filas de esta matriz; registrar propietario de control, evidencia o respuesta conservadora, usar `No corresponde` con prueba de no aplicabilidad. Guardar cambios, **no presentar aún revisión**.
4. En **Auditorías y certificaciones**, limpiar menciones internas no certificadas, guardar.
5. Obtener capturas del borrador sin tokens, códigos temporales, PII ni contraseñas y registrar revisión/fecha.
6. Completar controles faltantes, actualizar respuestas verificadas y recién entonces iniciar revisión pública de DIAGLOB.

## E. Puertas de cierre

- [ ] Nombre sin «Personalización» salvo finalidad probada.
- [ ] Email/Teléfono justificados o diseño de ingestión reducido.
- [ ] Las 16 respuestas reflejan estado efectivo, no proyección.
- [ ] Texto auditoría/certificaciones respaldado o vacío.
- [ ] Política incidentes aplicada y respaldos/aislamiento/retención/logs demostrados.
- [ ] Shopify Partner guardado en Borrador con capturas saneadas.
- [ ] Aprobación Shopify Nivel 2 recibida; prueba de recursos/errores PCD en app pública.
- [ ] App Store review final: NO-GO hasta evidencias anteriores.

**Fuentes internas:** `docs/security/shopify-security-evidence.md`, `docs/shopify-pcd-partner-submission-evidence-2026-10-20.md`, `docs/shopify-pcd-security-controls-2026-10-20.md`, `docs/security/incident-response-plan.md`, `docs/shopify-pcd-level2-customer-identity-isolation-2026-10-20.md`.
