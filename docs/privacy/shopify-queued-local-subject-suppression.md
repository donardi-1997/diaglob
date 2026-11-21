# Bloqueo de contactos después de `customers/redact` (tareas en cola)

**Control de seguridad, sin borrado adicional automático.** El alcance es la pareja organización/tienda, nunca el `Customer.id` global.

## Riesgo verificado en el código

Las campañas (`automation_execution_engine.process_recipient`) y los flujos (`automation_flow_engine.process_flow_recipient`) llaman a `evaluate_shopify_local_privacy` antes de enviar. Sin embargo, `customers/redact` elimina `CustomerStoreProfile` para la tienda: después de borrar la relación, una ejecución antigua podría conservar `local_customer_id` sin poder traducirlo a `customer.id` de Shopify. Depender solo de la resolución del ID externo y del correo/teléfono deja una brecha cuando cambió el contacto.

## Corrección

1. Durante el preview de `customers/redact`, mientras la relación original existe, se extrae el `customer_id` interno **de la tienda y organización verificadas**.
2. El plan de checkpoint incorpora un tombstone de tipo `local_customer` con HMAC de ID interno, identidad de tienda y clave de supresión persistente. No almacena ID, nombre, teléfono ni correo en texto claro.
3. El operador debe registrar el **checkpoint nuevo y completo** en el ledger externo independiente antes de emitir permisos, como ocurre con los demás tombstones. Las firmas previas se invalidan al cambiar el digest.
4. La redacción SQL y el tombstone se guardan en una misma transacción. Así, si un proceso antiguo intenta enviar por campaña o flujo después de eliminar el perfil Shopify, `evaluate_shopify_local_privacy` bloquea la coincidencia con el ID interno seudónimo, sin depender del perfil perdido.
5. El mismo `Customer.id` asociado con otra tienda sigue sin estar bloqueado allí, porque HMAC y consulta incluyen `organization_id` y `store_id`.

## Límites y revisión

- No garantiza supresión de mensajes que **ya fueron transmitidos** al proveedor ni colas ajenas que no consulten `evaluate_shopify_local_privacy`.
- No borra filas de campaña, intentos, contenido de mensajes, AI/embeddings ni exports; esas superficies siguen como controles separados.
- No hace `local_customer` tombstones para `shop/redact`: ya existe tombstone `shop` que bloquea ese alcance completo.
- Las pruebas demuestran coincidencia después de borrar el perfil y no afectación de otra tienda con el mismo `Customer.id`.
- No desplegar sobre datos reales sin regenerar el checkpoint externo validado; esta modificación altera el conteo y HMAC de la redacción prevista.
