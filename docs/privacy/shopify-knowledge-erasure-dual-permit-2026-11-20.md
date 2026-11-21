# Shopify shop/redact — autorización separada de eliminación de Knowledge Bases

> **Control de seguridad propuesto para revisión.** No certifica borrado real de documentos, embeddings ni S3 Vectors. No iniciar ejecuciones contra producción sin verificación jurídica y operacional.

## Motivo

La ruta de `knowledge-erasure` podía ejecutar borrados externos (S3, Bedrock) después de detectar el evento `local_redaction_executed`, sin confirmar una autorización nueva y específica de las KB a eliminar. El `scope_sha256` del SQL no representa necesariamente todas las KB exclusivas ni los cambios de vinculación posteriores.

## Nuevo flujo

1. Identificar el `shop/redact` original, validado por firma HMAC, organización/tienda, owner autenticado y un evento auditado de redacción SQL `local_redaction_executed`.
2. Calcular un plan de solo lectura con `plan_shop_knowledge_erasure`. Sólo entra `selected_stores` si el número exacto de tiendas vinculadas es uno y coincide con la solicitante. Bases organizacionales, compartidas y de otros tenants **se preservan**.
3. Calcular `knowledge_erasure_scope_digest` de `request_id`, `organization_id`, `store_id`, digest del evento de SQL, IDs exactos de KB exclusivas y conteo de compartidas. **No reutilizar el digest SQL para autorizar una eliminación diferente.**
4. Revisor jurídico autorizado firma una nueva `X-Privacy-Legal-Clearance` Ed25519 para ese digest y sus documentos de instrucción legal; operador técnico firma `X-Privacy-Execution-Permit` con operación **`shop_knowledge_erasure`**. Ambos TTL inferiores a 24h.
5. Antes de cualquier acción externa, el servidor verifica ambas firmas y recalcula el plan. Cambios en KB exclusivas o compartidas invalidan los permisos.
6. Ejecutar la función externa de eliminación sólo de las KB exclusivas. Fallos dejan paso abierto. La confirmación SQL de éxito **no prueba** que el almacén vectorial y todas las versiones S3 hayan desaparecido.
7. Mantener `fulfillment_complete=false` hasta evidencias independientes de S3, S3 Vectors, Google y demás procesadores correspondientes.

Los headers nuevos se exigen en el endpoint existente
`POST /api/stores/{store_id}/shopify/privacy/cases/{request_id}/knowledge-erasure`.
La API se mantiene autenticada y no devuelve contenidos de compradores.

## Pruebas y límites

```bash
cd backend
pytest -q tests/test_shopify_privacy_knowledge_erasure.py tests/test_shopify_privacy_local_execution.py tests/test_shopify_privacy_permit_tool.py tests/test_shopify_privacy_legal_clearance.py
```

- Tests sintéticos: rechazo sin firmas, rechazo sin segunda firma, rechazo si una KB antes exclusiva pasa a compartida tras aprobación, mantenimiento de otras tiendas, idempotencia y reintento tras fallo externo.
- Este cambio no ofrece un mecanismo de depuración de un documento de comprador individual en una KB compartida: esa tarea requiere trazabilidad fuente→tienda→cliente→vector, permisos granulares y verificación de borrado sin afectar a terceros.
- Los estados de proveedores externos y backups siguen abiertos hasta corroboración fuera del código.
