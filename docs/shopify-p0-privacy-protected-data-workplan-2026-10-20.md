# DIAGLOB — Plan de trabajo para cerrar los dos bloqueos Shopify P0

**Referencia:** [PR #265](https://github.com/donardi-1997/diaglob/pull/265) · [Privacidad #266](https://github.com/donardi-1997/diaglob/issues/266) · [Datos protegidos #267](https://github.com/donardi-1997/diaglob/issues/267)

**Alcance:** lista de tareas sin cronograma ni estimaciones. Se trabaja en una rama de auditoría; los cambios en producción, en los permisos de la aplicación Shopify y en los datos reales requieren aprobación independiente. Se conserva el requisito normativo de atender las solicitudes de privacidad dentro del plazo aplicable.

## Bloqueo A — Privacidad, exportación y eliminación real

- [ ] **A1. Inventariar todos los datos Shopify tratados por DIAGLOB:** consulta GraphQL/webhook/origen, organización/tienda/sujeto, modelos y columnas, API, archivos/adjuntos, conversaciones/IA, logs, métricas, colas, S3, índices, proveedores y copias de seguridad. **Entregable:** matriz con evidencia de archivo/línea, dueño, propósito, retención, acciones y huecos de cobertura.
- [ ] **A2. Aprobar la política de retención y excepciones:** identificar documentación comercial, obligaciones legales, copias de seguridad, plazos aplicables, encargados de tratamiento y criterios de eliminación sin afectar registros que deban conservarse.
- [ ] **A3. Revisar y consolidar la recepción firmada de los tres webhooks:** `customers/data_request`, `customers/redact`, `shop/redact`. Validar cuerpo original, HMAC, idempotencia, persistencia durable, reintentos, errores y aislamiento por tienda/tenant.
- [ ] **A4. Implementar el ciclo real de casos:** recepción → verificación de identidad y alcance → revisión legal → ejecución → verificación → cierre. Las tareas parciales, bloqueadas o delegadas a un tercero no podrán marcarse completadas.
- [ ] **A5. Implementar exportación real y segura:** extraer datos del sujeto correcto en todas las fuentes aplicables, respetar identificadores firmados y `orders_requested`, preparar artefactos cifrados y entregar al comerciante autenticado con auditoría y caducidad.
- [ ] **A6. Implementar redacción/borrado efectivo de cliente:** suprimir o eliminar datos permitidos en registros, derivados, IA, colas e índices; gestionar excepciones legales; impedir reingestión y evitar efectos sobre otras tiendas.
- [ ] **A7. Implementar borrado de tienda (`shop/redact`):** revocar y purgar exclusivamente los datos de la instalación Shopify afectada, sin borrar datos ajenos de la organización.
- [ ] **A8. Completar el tratamiento externo:** conectores, encargados de datos, proveedores, S3, backups, restauración, logging e índices; conservar evidencias de solicitudes, respuestas y excepciones.
- [ ] **A9. Implementar seguridad operativa:** roles, aprobación para borrados irreversibles, alertas de vencimiento, cola de revisión, recuperación de fallos, trazabilidad sin PII y auditoría del ciclo de vida.
- [ ] **A10. Ejecutar QA:** casos correctos/duplicados, firmas inválidas, proveedores caídos, legal hold, multi-tenant, reintentos, desinstalación/reinstalación, restauración de backups y pruebas con datos sintéticos.

**Criterio de cierre A:** las solicitudes obligatorias ejecutan las acciones legales aplicables; no hay falsos positivos de `fulfillment_complete`; la cobertura y los acuses de terceros se verifican; se conserva el aislamiento de tiendas y la evidencia de cumplimiento. **No basta con responder HTTP 2xx al webhook.**

## Bloqueo B — Datos protegidos de clientes Shopify

- [ ] **B1. Inventariar consumo real de campos y permisos:** clasificar cada lectura/escritura/webhook GraphQL; campo exacto, fuente, propósito, almacenamiento, visibilidad y función que lo usa. Separar PII entregada voluntariamente a DIAGLOB de PII leída desde Shopify.
- [ ] **B2. Evaluar scopes y función por función:** revisar `read_products`, `read_inventory`, `read_customers`, `read_orders`, `write_orders`, `write_draft_orders`, `read_merchant_managed_fulfillment_orders` y `write_merchant_managed_fulfillment_orders`; retirar los innecesarios cuando sea seguro.
- [ ] **B3. Determinar nivel y campos PCD:** documentar si DIAGLOB requiere nivel 1 y cuáles campos identificatorios de nivel 2 (nombre, correo, teléfono, dirección), justificando cada necesidad; no asumir que los scopes implican aprobación automática de todos los campos.
- [ ] **B4. Revisar protecciones técnicas:** cifrado en reposo y tránsito, segmentación tenant/shop/rol, minimización, retención, logging sin PII, acceso del equipo, seguridad de backup, eliminación y controles para datos usados por IA/analítica.
- [ ] **B5. Adaptar el comportamiento con permisos parciales/denegados:** GraphQL HTTP 200 con errores por campo, valores redactados/nulos, falta de scopes, revocación y reautorización. Deshabilitar funciones dependientes sin exponer datos de otro comerciante.
- [ ] **B6. Reconciliar Partner Dashboard con el código:** corregir la declaración actual «No necesita acceso a datos de clientes protegidos» si el inventario exige acceso; solicitar únicamente los permisos/campos justificados y completar la información de protección.
- [ ] **B7. Confirmar permisos reales en tienda de desarrollo:** instalación, grants de versión activa, lecturas permitidas/denegadas, cambios de scope, reautorización, revisión de Shopify y pruebas de regresión.
- [ ] **B8. Actualizar política de privacidad y ficha pública:** describir datos, finalidades, procesamiento, proveedores y controles exactamente como funciona la aplicación; no anunciar capacidades de borrado que no se hayan probado.

**Criterio de cierre B:** la declaración y aprobación de Shopify coincide con el comportamiento real; cada campo tiene justificación, controles y aprobación cuando aplique, y el producto funciona de manera segura ante datos no autorizados.

## Dependencias y orden de ejecución (sin tiempos)

1. **Arranque conjunto A1+B1+B2:** inventario de origen → operación → campo → almacenamiento → destino → borrado; mapa de scopes.
2. **Decisiones de producto y privacidad A2+B3:** definir necesidad real de PCD y alcance de retención/supresión antes de pedir permisos o borrar información.
3. **Implementación A3–A9+B4–B5:** cambios pequeños, con pruebas y revisión de seguridad en ramas separadas.
4. **Partner y documentación B6+B8:** tras inventario y controles confirmados, registrar lo que Shopify solicita.
5. **QA y cierre A10+B7:** pruebas reproducibles, evidencias vinculadas a commit/versión activa, aprobación del responsable de la aplicación.
6. **Reevaluación de publicación:** el cierre de estos dos bloqueos **no sustituye** instalación E2E, App Pricing, cuenta del revisor ni el AI Toolkit oficial.

## Estado del primer paso

- [x] Identificados los dos issues P0 y el PR de auditoría.
- [ ] Inventario compartido A1/B1 auditado y revisado.
- [ ] Matriz de scopes B2 con decisión definitiva de acceso.
- [ ] Implementación verificada y cierre formal.

**Referencias técnicas iniciales:** `backend/app/shopify_oauth.py`, `shopify.app.toml`, `backend/app/shopify_cod_orders.py`, `backend/app/shopify_orders.py`, `backend/app/shopify_sync.py`, `backend/app/services/shopify_fulfillment.py`, `backend/app/services/shopify_compliance_webhooks.py`, `backend/app/services/shopify_privacy_processing.py`, `backend/app/services/shopify_privacy_scoped_extraction.py`, `backend/app/services/shopify_privacy_suppression.py` y modelos de tenancy/PII.
