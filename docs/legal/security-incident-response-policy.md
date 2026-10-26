# Política de respuesta a incidentes de seguridad de DIAGLOB

**Versión:** `diaglob-security-incidents-2026-10-26`. **Propietario:** titular/operador de DIAGLOB. **Estado:** propuesta para adopción del titular; no certifica controles desplegados ni una auditoría independiente.

## Objetivo y alcance

Detectar, contener, investigar, notificar y recuperar incidentes que puedan afectar confidencialidad, integridad o disponibilidad de DIAGLOB, integraciones y datos de comerciantes/compradores. Incluye Shopify, identidad del personal, tokens, bases de datos, almacenamiento, IA, mensajería, proveedores, logs y backups.

## Responsabilidades

- **Responsable del incidente:** titular/operador de DIAGLOB; asigna suplente accesible, gravedad, recursos y decisiones. Hasta que se nombre otro, no se presume un SOC, DPO o equipo de guardia inexistente.
- **Responsable técnico:** persona autorizada de ingeniería/infraestructura designada por el titular; ejecuta contención y recuperación con registro de cambios.
- **Privacidad/legal:** responsable designado por el titular o asesor externo; evalúa obligaciones, titulares/comerciantes afectados, plazos y excepciones legales.
- **Comunicaciones:** titular o delegado expresamente autorizado; mantiene comunicación con comerciantes, Shopify, encargados y autoridades cuando corresponda.

Mantener contactos y suplencias en un directorio privado comprobado; nunca incluir contraseñas, tokens o información de compradores en esta política. El correo público de soporte del proyecto es un canal propuesto, no una guardia acreditada hasta verificar recepción y escalamiento.

## Clasificación y objetivos operativos

| Nivel | Ejemplo | Objetivo de actuación |
| --- | --- | --- |
| P1 crítico | Acceso entre tenants, exfiltración, claves comprometidas, ransomware o restauración que reactive datos borrados. | Escalar inmediatamente al titular; iniciar contención en la primera hora desde detección y mantener seguimiento continuo. |
| P2 alto | Acceso indebido acotado, sospecha fundada de fuga o pérdida de un control esencial sin alcance confirmado. | Acusar y asignar responsable en cuatro horas; contener sin demora y reevaluar como P1 si crece el alcance. |
| P3 moderado/bajo | Vulnerabilidad sin explotación conocida o interrupción sin indicios de exposición. | Registrar y asignar responsable el siguiente día hábil; definir y seguir una fecha de remediación. |

Son objetivos de la política; deben respaldarse con disponibilidad real del personal y canales. No constituyen métricas históricas ni garantías de servicio ya verificadas.

## Procedimiento

1. **Detectar y registrar:** crear identificador de incidente, hora UTC de detección/conocimiento, origen, servicios afectados, persona responsable y medidas iniciales. No adjuntar cuerpos completos, credenciales ni datos de compradores a tickets/chat de acceso general.
2. **Preservar evidencia:** conservar logs mínimos, hashes, referencias y cronología con acceso restringido, cadena de custodia y copias cifradas. Evitar que una limpieza o despliegue destruya evidencia necesaria; documentar las decisiones de retención.
3. **Contener:** aislar componentes/cuentas afectados, detener exportación, sincronización, colas y procesamiento comprometido, revocar sesiones/tokens según el alcance y bloquear accesos indebidos. Usar cambios autorizados y reversibles; no borrar indiscriminadamente datos o cuentas de otros tenants.
4. **Determinar alcance:** identificar tiendas/personas/categorías de datos, ventanas temporales, accesos efectivos, encargados y backups afectados. Diferenciar sospecha de evidencia confirmada. Una prueba sintética o ausencia de logs no demuestra ausencia de compromiso.
5. **Comunicar:** informar al titular y al responsable de privacidad inmediatamente en P1/P2. Como encargado, comunicar al comerciante afectado sin dilación indebida, con objetivo de primera información útil dentro de 24 horas de confirmar el incidente; no esperar a conocer todos los detalles. Cumplir contratos y plazos legales aplicables. Para GDPR, evaluar con el responsable/legal la notificación a la autoridad dentro de 72 horas desde conocimiento cuando corresponda; no extrapolar ese plazo a todos los países o roles. Contactar Shopify por sus canales oficiales y seguir sus instrucciones/obligaciones contractuales.
6. **Erradicar y remediar:** corregir causa raíz, permisos, credenciales, código/configuración y cobertura de pruebas. No restaurar secretos comprometidos. Rotar con planificación y preservar la recuperación de claves de cifrado/tombstones; una rotación no puede reactivar datos suprimidos.
7. **Recuperar:** verificar el artefacto limpio, esquema, controles de identidad/tenant y servicios. Restaurar backups aislados; contrastar el ledger externo y reaplicar supresiones antes de abrir webhooks/colas/tráfico. Si el checkpoint no coincide, mantener cuarentena y escalar.
8. **Cerrar:** el titular acepta la recuperación tras evidencia de contención, causa raíz, notificaciones y controles correctivos. Mantener pendientes externos visibles; no confundir recuperación técnica con cierre legal o con cumplimiento completo de una solicitud de privacidad.

## Contenido mínimo de una notificación

Identificador, naturaleza/fechas, alcance confirmado y aún desconocido, categorías de datos, efectos probables, medidas de contención/remediación, acciones recomendadas al comerciante, punto de contacto y próxima actualización. No divulgar datos de otras tiendas ni secretos; utilizar canal autenticado para información sensible.

## Registro, acceso y retención

Acceso por necesidad, cifrado de evidencia en reposo/tránsito y trazabilidad de lecturas/cambios. Objetivo de retención del expediente mínimo: 365 días tras cierre, sujeto a obligaciones, contrato, reclamaciones o legal hold documentado. Revisar y eliminar evidencia personal que deje de ser necesaria; un legal hold requiere responsable, fundamento y fecha de revisión, no conservación indefinida automática.

## Preparación y mejora

Verificar contactos/guardias y probar al menos anualmente un ejercicio de fuga de token, aislamiento entre tiendas y restauración con tombstones, además de hacerlo tras cambios relevantes. Realizar revisión posterior de P1/P2, con acciones, responsables y fechas. No declarar el ejercicio realizado sin registros verificables.

## Adopción

El titular debe confirmar responsables/contactos, comunicar esta política al personal y respaldar los objetivos con controles operativos antes de declararla adoptada en Shopify. La redacción del documento por sí sola no demuestra que las quince afirmaciones restantes del cuestionario PCD sean ciertas.
