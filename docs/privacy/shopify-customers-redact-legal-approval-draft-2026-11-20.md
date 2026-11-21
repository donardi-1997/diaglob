# DIAGLOB — Política propuesta de retención, bloqueo legal y supresión de compradores Shopify

> **BORRADOR v0.1 · 20 de noviembre de 2026 · NO APROBADO.**
> Documento preparado para revisión por el responsable autorizado de privacidad, asesoría jurídica y contable, y comerciantes aplicables. No habilita borrados reales, no sustituye instrucciones del comerciante, no certifica cumplimiento de Shopify y no constituye concepto jurídico.

## 1. Identificación y estado

| Campo | Valor |
|---|---|
| Identificador | `diaglob-shopify-customers-redact-legal-draft-20261120` |
| Producto | DIAGLOB (SaaS ecommerce) |
| Alcance | Datos personales de compradores y pedidos recibidos mediante tiendas Shopify conectadas y sus derivados dentro de DIAGLOB |
| Estado | **PENDIENTE DE REVISIÓN Y APROBACIÓN** |
| Responsable de privacidad DIAGLOB | **POR DESIGNAR / VALIDAR FACULTADES** |
| Aprobador jurídico | **PENDIENTE** |
| Aprobador contable/fiscal | **PENDIENTE**, para registros financieros |
| Comerciantes responsables | Identificar por tienda y contrato/instrucción |
| Fecha de aprobación / vigencia | **PENDIENTE** |
| Documento de instrucciones con el comerciante / DPA | **PENDIENTE DE CONTRASTAR** |

Para los datos procesados **por cuenta del comerciante** y de acuerdo con sus instrucciones, DIAGLOB se trata operativamente como *encargado del tratamiento* y el comerciante como *responsable*. Esta caracterización debe confirmarse por flujo y contrato; para datos de facturación propia de DIAGLOB podrían existir roles distintos. No asumir que la instrucción de una tienda autoriza borrar información de otra.

## 2. Base externa y distinción entre plazos

- Shopify: los webhooks de cumplimiento incluyen `customers/data_request`, `customers/redact` y `shop/redact`. Validar el HMAC del cuerpo original y responder `401` ante firma inválida. La acción solicitada debe completarse dentro de **30 días** desde su recepción, salvo conservación legítima documentada.
  - https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
  - https://shopify.dev/docs/apps/build/webhooks/subscribe
- Colombia: Ley Estatutaria 1581 de 2012, Decreto 1074 de 2015 y doctrina SIC: el titular puede solicitar supresión; el ejercicio debe armonizarse con deberes legales o contractuales de conservación. Si existe obligación de retener, limitar accesos y finalidades al mínimo requerido.
  - https://sedeelectronica.sic.gov.co/sites/default/files/normatividad/Ley_1581_2012.pdf
  - https://sedeelectronica.sic.gov.co/publicaciones/boletin-juridico/concepto/derecho-la-tranquilidad-y-supresion-de-datos-personales-0
  - https://sedeelectronica.sic.gov.co/publicaciones/boletin-juridico/concepto/el-encargado-no-puede-hacer-analisis-de-datos-sin-instruccion-del-responsable

**No confundir** plazo operativo de respuesta Shopify (30 días) con el periodo legal de conservación de facturas y otros registros. Los valores del repositorio `backup_expiry_target_days=30` y `closure_audit_retention_target_days=365` son **objetivos técnicos propuestos** en `config/shopify-privacy-policy.json`, no determinaciones jurídicas automáticamente aprobadas.

## 3. Regla de supresión y segregación por tienda

1. El webhook se incorpora mediante HMAC verificado, referencia opaca de caso, identificación de tienda resuelta y deduplicación.
2. El alcance exige coincidencia exacta de `organization_id`, `store_id`, dominio Shopify verificado, `customer.id` y `orders_to_redact` si Shopify los proporciona. Rechazar IDs ambiguos, duplicados o ajenos; no usar similitud de correo/teléfono como prueba autónoma de identidad.
3. Generar manifest y vista previa sin exponer PII. Resolver cada campo por procedencia de tienda, cliente y pedido.
4. Antes de toda mutación, verificar las excepciones de retención y cualquier bloqueo legal aplicable **a ese caso** con instrucción/evidencia atribuible al responsable pertinente. `legal_hold=false` dentro del permiso no es por sí mismo evidencia de la revisión.
5. Preservar los registros compartidos con otra tienda: eliminar o anonimizar solo las relaciones, copias y atributos originados en la tienda solicitante. Si no se puede distinguir procedencia de un campo, **bloquear y escalar**, nunca borrar un registro global por inferencia.
6. Preparar/activar tombstones acotados por tienda para evitar reingesta, marketing y recontacto indebidos; retener el mínimo seudónimo necesario bajo control de acceso.
7. Borrar/anonimizar los datos autorizados y conservar temporalmente solo la fracción indispensable por base legal documentada. Toda retención excepcional deberá quedar segregada de campañas, IA, operativa ordinaria y exports no autorizados.
8. Verificar SQL, colas, automatizaciones, agentes/IA, índices/vector stores, archivos/versiones, terceros, respaldos y restauraciones antes de certificar el caso.
9. Conservar evidencia no sensible de acciones, verificaciones, bloqueos, caducidades, revisión independiente y decisiones; no consignar contenido del comprador en Git, CI o expedientes públicos.

## 4. Matriz de decisiones de retención (requiere aprobación)

| Control del backend | Regla propuesta después de `customers/redact` | Retención excepcional / verificación pendiente |
|---|---|---|
| `customer_contact` | Eliminar o anonimizar nombres, correos, teléfonos, direcciones y perfil exclusivo de la tienda; romper vínculos comerciales | Obligación individual acreditada o relación ajena a la tienda solicitante |
| `financial_orders` | Suprimir contacto/direcciones no imprescindibles, conservar solo asiento/comprobante mínimo exigido bajo acceso restringido | **Asesor contable/jurídico** determina norma, jurisdicción, hecho inicial y plazo; no fijar plazo universal |
| `shipping_and_returns` | Retirar destinatario, direcciones, etiquetas y referencias cuando cesa su necesidad; notificar operadores pertinentes | Envíos, devoluciones o reclamaciones abiertas y retención contractual/legal verificable |
| `conversations` | Eliminar o anonimizar mensajes, transcripciones, adjuntos, previsualizaciones y exportaciones asociadas | Litigio, investigación u obligación específica documentada; conservar únicamente fragmentos mínimos |
| `automations_and_ai` | Cancelar destinatarios/tareas pendientes, quitar campañas, prompts, respuestas, documentos, embeddings, índices y derivados identificados | Si no se demuestra procedencia y borrado, mantener caso abierto; no inferir que eliminar la KB elimina el vector store |
| `logs_and_audit` | Evitar PII en logs; conservar evidencia técnica mínima de recepción, decisión, operación y fallo/reintento | Finalidad de seguridad/obligación aplicable con acceso limitado, fecha de expiración y auditoría |

**Todos los plazos legales, eventos de inicio, jurisdicciones, excepciones y bases normativas quedan PENDIENTES.** La tabla no autoriza modificaciones reales ni permite atestaciones `approved` todavía.

### Criterios por categoría

Para cada categoría deberán adjuntarse de forma privada: (a) finalidad y base jurídica, (b) jurisdicción, (c) evento inicial del cómputo, (d) periodo de conservación aprobado, (e) atributos mínimos conservables, (f) destinatarios/procesadores, (g) prueba de excepción o ausencia de excepción, (h) firma y fecha del revisor independiente. El registro técnico conserva únicamente referencias opacas/digests cuando sea suficiente.

## 5. Matriz de bloqueo legal por caso (obligatoria)

| Campo del registro de decisión | Regla |
|---|---|
| `request_id` | Identificador opaco de recibo HMAC-verificado |
| `organization_id`, `store_id`, `shop_id` | Vinculación exacta, sin copiar datos personales |
| `scope_sha256` | Hash del manifest aprobado; se invalida si cambia el alcance |
| `hold_status` | `not_reviewed` (predeterminado), `active`, `cleared` |
| `hold_basis` | Referencia privada a causa y alcance del bloqueo, cuando proceda |
| `merchant_instruction_reference` | Instrucción válida del comerciante o registro de su base de actuación |
| `independent_review` | Aprobador, rol, fecha UTC, firma y artefacto restringido |
| `expires_at` | Caducidad de la decisión y obligación de reconfirmar si cambia el caso |
| `policy_sha256` | Digest de la política legal vigente/aprobada |

**Regla fail-closed:** `not_reviewed`, firma ausente, referencia no validada, discrepancia de tienda/sujeto/alcance o bloqueo activo impiden redacción destructiva de datos afectados. Un `active` no necesariamente impide la supresión de datos no sujetos al bloqueo: requiere una decisión aprobada, granular por categoría, no un booleano genérico.

El código actual en `backend/tools/shopify_privacy_permit.py` emite `legal_hold=False` dentro del permiso. **Brecha P0 pendiente:** verificar de manera independiente una autorización por caso (firmada y ligadamente al alcance) antes de permitir que esa aseveración habilite la mutación. Hasta implementarla, no considerar el permiso como aprobación jurídica.

## 6. Separación entre controles de programa y evidencia de cada caso

- **Programa:** atestaciones Ed25519 de las seis categorías de retención, `legal_holds`, procesadores y restore, ligadas a digest de política. Útiles para liberar controles de lanzamiento, **no** prueban una supresión individual.
- **Caso:** recibo firmado por Shopify, manifest, verificación de procedencia, decisión legal del caso, permiso de ejecución de menos de 24 h, checkpoint independiente, resultados de redacción, confirmaciones de terceros y revisión final.
- Los artefactos legales deben almacenarse en un repositorio restringido, con control de versiones/acceso y, cuando corresponda, conservación inmutable. Publicar solo resúmenes desidentificados y SHA-256 en Git.
- `fulfillment_complete` permanece `false` hasta comprobar todas las superficies aplicables. En caso de duda sobre el cumplimiento del plazo, escalar en vez de falsear estados.

## 7. Acta de aprobación (NO FIRMADA)

**Responsable del tratamiento/comerciante y base de instrucciones:** PENDIENTE.

**Responsable de privacidad DIAGLOB (nombre, cargo, facultades):** PENDIENTE.

**Revisión jurídica de jurisdicción, bases legales, retención y holds:** PENDIENTE.

**Revisión contable/tributaria de `financial_orders`:** PENDIENTE.

**Excepciones aceptadas y evidencia privada:** PENDIENTE.

**Fecha UTC de aprobación y vigencia:** PENDIENTE.

**Digest SHA-256 de la versión aprobada:** PENDIENTE.

**Firma del aprobador autorizado:** PENDIENTE.

> No sustituir estos campos por valores ficticios ni emitir atestaciones `approved` hasta completar la revisión sobre evidencia original.

## 8. Relación con el código

- Política técnica vinculada: `config/shopify-privacy-policy.json`.
- Firmas de controles: `backend/app/services/shopify_privacy_attestations.py`.
- Permiso por caso: `backend/app/services/shopify_privacy_execution_authorization.py`.
- Ejecución local parcial: `backend/app/services/shopify_privacy_local_execution.py`.
- Matriz operativa de proveedores: `docs/shopify-privacy-evidence-pack-2026-10-26.md`.
- Auditoría de superficies externa actualizada: `docs/privacy/shopify-customers-redact-external-evidence-2026-11-20.md`.
