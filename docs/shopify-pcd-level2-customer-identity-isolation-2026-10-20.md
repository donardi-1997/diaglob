# Shopify PCD Level 2 — Aislamiento de identidad y requisitos de aceptación

Fecha: 2026-10-20. Revisión de código, sin inspección de datos de clientes reales.
**Estado: PENDIENTE de aprobación Shopify Partner y validación operativa.**

## Clasificación

DIAGLOB procesa datos protegidos de comprador en eventos de pedidos Shopify,
aunque no utilice el scope de consulta masiva `read_customers`. Según
[Shopify Protected Customer Data](https://shopify.dev/docs/apps/launch/protected-customer-data),
el **Nivel 1** cubre datos vinculados a un consumidor sin campos
identificatorios; el **Nivel 2** es necesario cuando se utilizan nombre,
dirección, correo electrónico o teléfono.

| Origen / función | Dato protegido | Campo identificatorio | Uso actual | Decisión |
| --- | --- | --- | --- | --- |
| `orders/create`, `orders/updated`, `orders/cancelled` | `customer.id`, order ID, line items, estados | Nivel 1, sin los cuatro campos por sí solos | Pedido, seguimiento e identidad de tienda | Declarar PCD |
| Esos mismos webhooks | `customer.first_name`, `last_name`, `shipping_address.name` | **Name — Nivel 2** | Destinatario y relación cliente/pedido | Solicitar si es necesario en fulfillment |
| Esos mismos webhooks | `shipping_address.address1/address2/zip` | **Address — Nivel 2** | Destino físico del envío | Solicitar si se usa entrega domiciliaria |
| Esos mismos webhooks | `customer.email`, `order.email` | **Email — Nivel 2** | Dato de contacto/enlace de identidad | Justificación funcional y reducción pendientes |
| Esos mismos webhooks | `customer.phone`, `shipping/billing_address.phone` | **Phone — Nivel 2** | Contacto en entrega y relación de identidad | Validar necesidad por función |
| `customers/data_request`, `customers/redact`, `shop/redact` | Identificadores y selectores de solicitudes | Pueden contener email/teléfono | Privacidad/retención, sin exponerlos a UI | Proteger, retener y procesar según base legal |
| Admin GraphQL `products`, `shop` | Producto/comercio | No identificatorios por sí mismos | Catálogo y conexión | No justificar Nivel 2 con estos |
| Admin GraphQL `orderCreate`, `draftOrderCreate` | DIAGLOB envía PII a Shopify en payloads | Puede incluir nombre/contacto/envío | Operaciones de comercio | Separar datos *enviados* de campos Shopify *leídos* |

**Conclusión:** Nivel 2 sigue requerido para los flujos descritos hasta demostrar
que las cuatro categorías no se necesitan y rediseñar la ingestión. No inferir
aprobación a partir de scope parity (8/8) o sincronización de productos POC.

## Hallazgo de seguridad corregido en código

`shopify_webhook_service._upsert_customer` podía reutilizar registros
`Customer` compartidos de la misma organización por simple teléfono/correo,
aunque pertenecieran a **otro Shopify shop** o representaran **otro Shopify
customer ID**, y sobrescribir nombre/telefono/correo a nivel organización.

La modificación en este frente aplica el principio de menor vinculación:

1. Un `external_customer_id` de Shopify solo encuentra cliente por perfil
   **del mismo store + ID Shopify exacto**; no hace fallback por contacto.
2. Sin ID Shopify (comprador invitado), solo se reutiliza un perfil **guest** de
   la misma tienda, sin perfiles en otras tiendas. La igualdad de contacto
   entre dos tiendas no es prueba de identidad.
3. Si un registro histórico está vinculado a varias tiendas, la ingestión de
   un webhook de una de ellas **no sobrescribe** los campos de contacto
   compartidos. La dirección específica sigue asignada al pedido de la tienda.
4. El control de supresión de privacidad existente sigue pudiendo impedir
   el fallback de contactos.
5. Pruebas sintéticas multi-tienda comprueban los puntos anteriores; no se
   afirman datos históricos limpiados ni ausencia de otros callsites riesgosos.

El cambio deliberadamente **puede crear registros separados** para compradores
que comparten contacto pero no un ID Shopify confiable. La reconciliación de
identidades se decidirá con reglas explícitas por tienda y pruebas de privacidad,
no mediante un merge automático de datos personales.

## Shopify Partner — tareas del propietario (no ejecutadas en este PR)

- Abrir la **aplicación DIAGLOB existente**, no crear otra: **API access requests
  → Protected customer data access → Request access**.
- Documentar finalidad concreta de los pedidos, solicitar PCD y **solo los campos
  Name, Address, Email, Phone efectivamente indispensables**. La necesidad de
  correo/teléfono y su minimización aún necesita revisión comercial/legal.
- Completar **Data protection details** con evidencia comprobada de cifrado en
  reposo/tránsito y respaldos; segregación test/prod; retención, consentimiento y
  opt-out según corresponda; acceso staff y logs; DLP, contraseñas fuertes,
  respuesta a incidentes y contratos con comerciantes/proveedores.
- Guardar captura saneada de selección/estado de revisión y aprobación.
  Probar valores `null`, campos redactados y HTTP 200 con `errors`.
- No afirmar aprobación ni cumplimiento mientras faltan pruebas reales
  de restauración/backup cifrado, acceso del personal, retención y
  exportación/redacción GDPR de extremo a extremo.

**Criterio de cierre:** Partner aprobado para los campos concretos solicitados,
controles Nivel 1+2 probados en producción de forma responsable y pruebas
positivas/negativas en tienda de desarrollo. `App Store NO-GO` hasta entonces.

Referencias: `docs/shopify-pcd-partner-submission-evidence-2026-10-20.md`,
`docs/security/shopify-security-evidence.md`,
`docs/shopify-p0-initial-data-inventory-2026-10-20.md`,
`docs/shopify-devstore-e2e-acceptance-matrix-2026-10-20.md`.
