# Shopify GDPR — recuperación de identidad histórica firmada (P0 #266)

Este recurso es **solo para operadores autorizados**. No borra datos, no genera
exportaciones, no contacta a Shopify y no marca solicitudes como completadas.

## Incidencia observada

En el monitor de producción (23 oct 2026) hay una solicitud HMAC-auditada de
`shop/redact` con diez tareas, pero sin `organization_id`/`store_id` vinculados.
La aplicación **no puede asociarla a la tienda POC por intuición o dominio**.

## Nueva operación controlada

`POST /api/internal/shopify/privacy/cases/{request_id}/repair-identity`
con `X-Internal-Secret` válido, que requiere primero habilitar la revisión
interna con el script de PR #306 y un usuario/operador autorizado.
El `request_id` es el digest SHA256 interno del caso; obtenerlo por canal
operativo autenticado `GET /api/internal/shopify/privacy/cases`, nunca desde
capturas de datos personales ni logs públicos.

La reparación exige TODOS estos hechos independientes:

1. Recibo firmado y auditado con actor `shopify_hmac_verified`, más
   `processing_prepared` y exactamente diez tareas sin completados falsos.
2. Registro previo `ShopifyPrivacyShopIdentity` cuyo **ID numérico de
   Shopify y dominio** sean idénticos al recibo y vincule un tenant/store único.
3. Procedencia `hmac_uninstall` o `hmac_compliance`, creada antes del
   recibo. Para `shop/redact` exige además uninstall HMAC auditado ANTES de
   la fecha del recibo; no se fabrica una huella histórica a posteriori.
4. La fila Store actual debe seguir perteneciendo al tenant original y su
   dominio, si figura, no puede diferir del dominio firmado. Otra solicitud
   firmada con shop-ID/domain o vinculación contradictoria bloquea.
5. Caso aún pendiente, sin cambios manuales de estado ni conclusión inventada.

Si no existe un registro histórico exacto, devuelve error
`SIGNED_SHOP_HISTORY_MISSING` o `SIGNED_SHOP_HISTORY_UNVERIFIED`,
**sin modificar ningún dato**. Nunca utiliza una conexión actual como
sustituto de la vinculación histórica; nunca copia el tenant de otra tienda.

Cuando la evidencia coincide, actualiza exclusivamente `organization_id` y
`store_id` del recibo, y anexa un evento de auditoría sanitizado. Repetir la
operación es idempotente. Retorna siempre
`fulfillment_authorized=false` y `fulfillment_complete=false`.

## Revisión indispensable antes del borrado real

- Verificar por canal privado la autenticidad de la entrega Shopify y la
  instalación/desinstalación original, incluidos conflictos de identidad.
- Identificar propietarios de Customer compartidos, pedidos contables,
  conversaciones y derivados con vínculo a la tienda/sujeto.
- Aprobar retención, excepciones contables y legal hold por jurisdicción.
- Obtener verificación de procesadores externos, colas y respaldos.
- Implementar export/redact reales con auditoría y confirmación independiente.
- No generar ni completar borrados automáticamente: los tests solo utilizan
  SQLite aislado.

El monitor `app.shopify_privacy_sla_watch` sigue fallando/alertando por un
recibo sin alcance confirmado. Una reparación técnica **no es prueba de
cumplimiento** del derecho de supresión y no desactiva las obligaciones de
retención/revisión.
