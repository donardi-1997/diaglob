# Política de privacidad, retención y derechos — integración Shopify

**Versión:** `diaglob-shopify-privacy-2026-10-26`. **Fecha:** 26 de octubre de 2026.

Política técnica propuesta por solicitud del titular de DIAGLOB. No es un dictamen jurídico, una certificación de controles ya desplegados ni una declaración de aprobación PCD. Antes de publicarla o activar tratamiento real, el responsable debe confirmar la identidad jurídica/contactos del proveedor, contratos, jurisdicciones, encargados y controles efectivos. No se publicará automáticamente.

## 1. Roles y finalidad

El comerciante determina las finalidades y las instrucciones sobre los datos de su tienda. DIAGLOB trata las copias necesarias para catálogo, asistencia, gestión de pedidos y funcionalidades contratadas. Los datos de cuentas/facturación de DIAGLOB se gestionan separadamente de los datos de compradores. No se usa la instalación, un dominio ni un JWT como consentimiento para acceder a otra organización.

No vender datos personales ni utilizar datos de una tienda para publicidad, entrenamiento general de modelos o fines ajenos al servicio sin base jurídica, contrato y permisos aplicables. Una integración publicitaria requiere sus propias decisiones de consentimiento; instalar DIAGLOB no las sustituye.

## 2. Minimización y datos

Solicitar solo scopes y campos indispensables: identificadores Shopify, productos/pedidos, nombre, email, teléfono y dirección cuando la función efectivamente los requiera. Los datos personales de pedidos siguen siendo datos protegidos aunque no se solicite `read_customers`.

No almacenar credenciales de compradores ni tarjetas. Los pagos de compras Shopify permanecen en Shopify Checkout. Los tokens del proveedor se cifran y no se exponen a frontend, logs o capturas. Las exportaciones privadas se cifran en reposo y se entregan exclusivamente por HTTPS a un propietario autorizado mediante un ticket personal de un solo uso.

## 3. Solicitudes y plazos

- Acusar recibo únicamente tras verificar HMAC y persistir duraderamente la solicitud. El HTTP 2xx **no** acredita cumplimiento.
- Verificar la identidad exacta de shop/sujeto y el alcance por organización/tienda antes de revelar o modificar datos. No resolver ambigüedades por coincidencia de email/teléfono entre tiendas.
- Gestionar las acciones dentro de **30 días de recibir** el webhook. Si una obligación legal impide una parte del borrado, no declararla completada: documentar categoría, fundamento, responsable, mínimo retenido y vencimiento; informar al comerciante.
- `customers/data_request`: entregar al propietario de la tienda la información del sujeto y pedidos indicados, junto con cobertura, exclusiones y copia de los procesadores que corresponda. Una exportación parcial debe identificarse como parcial.
- `customers/redact`: borrar o disociar las copias personales atribuibles al sujeto y a los pedidos indicados; detener colas/envíos y bloquear reingesta.
- `shop/redact`: tramitar el borrado de datos de la tienda tras la notificación de Shopify posterior a la desinstalación. No borrar otras tiendas, cuentas compartidas ni obligaciones propias de facturación indiscriminadamente.

## 4. Retención y disposición

| Categoría | Regla por defecto | Excepción/control |
| --- | --- | --- |
| Contacto, direcciones, conversaciones y contenido de compradores | Solo mientras sea necesario para la función contratada; ante solicitud válida, borrar/disociar dentro del plazo anterior. | Una retención distinta necesita instrucción documentada y revisión por caso; no hay excepción automática por país o fecha del último pedido. |
| Copias de pedidos | El registro autoritativo del comerciante permanece en Shopify. Eliminar los campos personales y vínculos de la copia DIAGLOB que no deban conservarse. | Si el comerciante acredita una obligación fiscal/contractual específica, conservar exclusivamente el mínimo, restringido y con vencimiento definido; no inventar un plazo fiscal universal. |
| Identidad compartida entre tiendas | Desvincular la tienda/sujeto y usar referencias disociadas en sus registros. | No destruir campos cuyo origen/finalidad pertenezca a otra tienda; mantener el caso en revisión para cualquier dato compartido no atribuible. |
| Exportaciones temporales | Ticket de **15 minutos**, ligado al usuario/tienda/caso, un solo uso. Purgar el cifrado al descargar, revocar o expirar. | No adjuntar a email, URL ni sistemas de logs. La entrega parcial no cierra la solicitud. |
| Colas, automatizaciones, IA y archivos | Cancelar procesamiento y eliminar/disociar contenido atribuible, incluidos prompts, respuestas, adjuntos, índices y derivados. | Si no hay atribución demostrable, revisión manual; no declarar ausencia por no hallar una clave foránea. |
| Logs y evidencias de cierre | Evitar cuerpos, selectores y secretos; conservar evidencia mínima y acceso restringido con objetivo máximo de **365 días** tras cierre. | Es un objetivo propuesto, sujeto a confirmar con seguridad/legal y contratos; los identificadores seudónimos también están protegidos. |
| Backups | Objetivo de caducidad máxima **35 días**; cifrado, aislados y no usados para operación normal. | Confirmar técnicamente todas las copias/versiones/proveedores. Un backup más largo debe corregirse o documentarse, no certificarse por esta política. |
| Tombstones/anti-reingesta | HMAC con clave estable y contexto de tienda; conservar mientras puedan volver datos de backups/reintentos/procesadores. | Registro externo al backup restaurable, clave recuperable de forma segura y checkpoint verificado **antes** de reabrir ingestión. No conservar identificadores crudos innecesarios. |

Los objetivos de retención no prueban una configuración de producción existente. No usar esta tabla para borrar documentación financiera retenida legalmente ni para retener toda la información personal por defecto.

## 5. Procesadores y restauraciones

Mantener un registro efectivo por tenant/tienda de los proveedores usados, finalidades, ubicación/transferencias, contratos, identificadores de solicitudes y constancia de exportación/borrado. Incluye, cuando estén conectados, mensajería WhatsApp/Instagram/email, proveedores CJ/Dropi/logística, Meta, AWS/Bedrock y almacenamiento/Knowledge, observabilidad y backups. Esta lista es un inventario de revisión, **no** afirma que todos sean subencargados activos ni que sus contratos o plazos estén verificados.

Enviar instrucciones a cada encargado aplicable y obtener confirmación. Un mock o un hash presentado sin verificar no es confirmación del proveedor. Al restaurar, aislar el entorno, recuperar tombstones desde el registro independiente, comparar checkpoint y reaplicar supresiones **antes** de webhooks, sincronización, colas o acceso normal. Una discrepancia debe bloquear el tratamiento y escalarse.

## 6. Autorización y seguridad

Separar preparación, autorización y ejecución. Una operación real necesita política adoptada por el operador y una autorización por caso/acción, de duración acotada y ligada al alcance revisado; una marca booleana del navegador o un secreto interno compartido no bastan para entregar datos de compradores.

Exigir control de acceso mínimo, cifrado de datos y backups, autenticación robusta de personal, registros de acceso y respuesta a incidentes. Validar esas medidas antes de contestar afirmativamente el cuestionario PCD. No incluir credenciales reales en la política, vídeos, repositorio ni conversación.

## 7. Cierre y contacto

Cerrar solo tras demostrar todas las superficies aplicables, entrega o disposición efectiva, excepciones legales, procesadores, backups y protección contra reingesta. El procesamiento de unas tablas locales nunca autoriza `fulfillment_complete=true` para todo el caso.

Canal propuesto de coordinación: `support@diaglob.tech`, ya utilizado por el proyecto. Antes de publicación, verificar titularidad, recepción y monitorización; la existencia de la dirección en código no lo acredita. Los comerciantes deben poder ejercer derechos sin enviar contraseñas o tokens.

## 8. Adopción y revisión

Antes de activar: responsable jurídico/operativo identificado; revisión de jurisdicciones y contratos; pruebas PostgreSQL/concurrencia y recuperación; procesadores/backups inventariados; endpoints desplegados verificados y permisos PCD correctos. Revisar ante cambios de finalidad, campos, proveedores, legislación o incidentes. El archivo técnico [config/shopify-privacy-policy.json](../../config/shopify-privacy-policy.json) fija parámetros reproducibles, no sustituye esta revisión ni activa ejecución.
