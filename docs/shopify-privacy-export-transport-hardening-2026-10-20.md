# DIAGLOB — Seguridad del transporte de exportación Shopify (2026-10-20)

**Estado: transporte de datos sintéticos únicamente. NO está habilitado un exportador ni una entrega de datos personales de producción.**

Este cambio refuerza `shopify_privacy_secure_delivery.py`, que emite y consume tickets de un solo uso cifrados y ligados a una solicitud firmada de Shopify. La habilitación sigue exigiendo `SHOPIFY_PRIVACY_SYNTHETIC_HTTP_ENABLED=true` **y** SQLite exclusivamente en memoria; no existe ruta productiva de emisión y los resultados siguen marcados `synthetic_only=true` y `fulfillment_complete=false`.

## Invariantes añadidas

1. **Tienda no eliminada y activa**: se valida también `Store.active=true`, no solo `deleted=false`.
2. **Aislamiento de identidad Shopify**: `ShopifyPrivacyRequest.shop_domain` debe normalizarse al mismo dominio que `Store.shopify_domain`; debe existir `ShopifyPrivacyShopIdentity` persistida con el **mismo** `shop_id`, dominio, organización y tienda. Un `store_id` reutilizado, relink o historial perdido no autoriza entregar nada.
3. **Revalidación continua**: estas condiciones se ejecutan al emitir, **redeem** y revocar, junto con los permisos actuales del usuario. La solicitud debe permanecer con estado `pending_policy_review` y sin `completed_at`.
4. **Integridad en dos niveles**: tras descifrar y comprobar SHA-256 de los bytes del archivo, la descarga descifra y valida de nuevo el *sobre interno* `diaglob.shopify.synthetic`: `request_id`, esquema, `synthetic_only`, cantidad de filas y marcadores de campos sintéticos. Un documento manipulado, incluso con una capa externa cifrada y checksum recompuestos, no se devuelve.
5. **Fallo seguro**: si el contenido interno no cumple el contrato, se revierte la transacción, el ticket no se marca como canjeado y no se devuelve ningún archivo. Los errores externos de la API permanecen genéricos.

## Pruebas sintéticas

```bash
cd backend
pytest -q tests/test_shopify_privacy_secure_delivery.py tests/test_shopify_privacy_synthetic_export.py
```

Incluye casos de tienda desactivada/eliminada, cambio de dominio Shopify después de emitir un ticket, ausencia/conflicto de historial firmado, estado de caso completado, corrupción del sobre interno con hash y cifrado exterior nuevos, y verificación de que el ticket permanece sin consumir.

## Pendientes antes de autorizar exportación real

- Validar formalmente los **derechos del destinatario**, la identidad de la tienda desde Shopify y las decisiones de entrega posteriores a desinstalación; una fila histórica firmada no es por sí sola una autorización de acceso.
- Cobertura completa de datos con procedencia **por tienda y sujeto**: cliente compartido, pedidos, artículos, conversaciones, automatizaciones, IA, archivos y subprocesadores.
- Decisiones legales de conservación y excepciones; gestión de solicitudes que exceden los límites de exportación, consultas incompletas, reintentos y entregas denegadas.
- Diseño independiente de aprobación, cifrado/rotación de llaves, entrega autenticada, expiración, purga periódica, registro mínimo y confirmación de recepción.
- Pruebas E2E en tienda Shopify de desarrollo, revisión de los webhooks registrados en la versión activa y autorización explícita para habilitar tratamiento real.

**Prohibido interpretar la prueba sintética o el merge como cumplimiento GDPR real o autorización de datos protegidos en Shopify Partner.**
