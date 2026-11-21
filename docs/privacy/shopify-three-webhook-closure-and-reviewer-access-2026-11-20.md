# DIAGLOB — Tres webhooks, evidencia por caso y acceso para la revisión Shopify

> Fecha del corte: 20 de noviembre de 2026. **PLAN OPERATIVO / EVIDENCIA PARCIAL**, sin certificación de cumplimiento, sin aprobación jurídica ni acceso de auditor ya creado. No usar datos personales reales para demostrar el flujo.

## 1. Contrato de diez verificaciones por solicitud

| Área obligatoria | `customers/data_request` | `customers/redact` | `shop/redact` |
|---|---|---|---|
| `signed_receipt` | HMAC válido sobre cuerpo original + audit | Igual | Igual |
| `shop_identity` | Tienda original autenticada | Igual | ID/dominio Shopify incluso tras uninstall |
| `subject_linkage` | `customer.id`, `orders_requested` exactos | `customer.id`, `orders_to_redact` exactos | Todas las relaciones de **esa** tienda, sin incluir otras |
| `local_structured_records` | Exportación estructurada acotada | Anonimización/borrado por procedencia | Anonimización/borrado por tienda |
| `ai_and_unstructured_content` | Consolidar documentos, prompts, respuestas, KB, vectores y archivos atribuibles | Borrado/verificación del comprador | Eliminar KB exclusiva y fuentes; las compartidas requieren depuración granular |
| `automation_and_queues` | Incluir ejecuciones/destinatarios pertinentes | Suspender recontacto, pendientes y reintentos | Suspender todos los trabajos de la tienda |
| `external_processors` | Consultar datos accesibles; recibir respuestas | Acreditar eliminación o excepción por proveedor aplicable | Acreditar eliminación o excepción para la tienda |
| `retention_and_legal_holds` | Identificar restricciones de entrega/retención | Decisión documentada por caso, no mero booleano del operador | Decisión documentada por categoría, tienda y excepciones |
| `backups_and_reingestion` | Revisar copias/retenciones | Ledger externo, tombstones, restore/replay test | Igual, además tombstone de tienda |
| **`merchant_delivery` / `reimport_suppression`** | Entrega segura al comerciante verificado y confirmada | Supresión activa, pruebas de no reingesta/recontacto | Supresión de tienda + `knowledge-erasure` después del SQL |

**Invariante:** cada caso tiene exactamente nueve controles comunes y un décimo específico. Un recuento de 10 filas no demuestra ejecución de los diez pasos: estados de tareas, evidencias originales y resultados se validan por separado.

## 2. Flujo actual y punto de cierre

- **Webhook:** Shopify requiere `application/json`, HMAC válido, `401` cuando el HMAC sea inválido, y respuesta HTTP 2xx para confirmar recepción. El requisito de actuación se cumple en un plazo de **30 días**, salvo conservación legal documentada; **acuse HTTP ≠ cumplimiento**.
- **`customers/data_request`:** existe exportación local con permiso Ed25519 vinculado a tenant/tienda/caso/manifest. `local_export` es parcial, con ticket cifrado, un solo uso y destinatario owner. **No certifica la extracción IA, colas, archivos, proveedores externos ni la entrega completa al comerciante.**
- **`customers/redact`:** existe redacción parcial SQL, tombstones y checkpoint de restore. En la rama de seguridad independiente se propone una segunda firma legal; **no confundir PR pendiente con código desplegado**. Toda identidad compartida entre tiendas debe preservarse y suprimir solo las copias/relaciones atribuibles a la tienda solicitante.
- **`shop/redact`:** `knowledge-erasure` debe ir después de `local_redaction_executed`; solo bases exclusivas de esa tienda. Bases organizacionales/compartidas o documentos con procedencia ambigua son bloqueos abiertos, nunca objetos a borrar indiscriminadamente.
- **Sin datos atribuibles:** los recibos históricos con estado `no_data_attributable` no llevan `completed_at`. El código deja tareas `not_applicable` y conserva audit; eso es una **determinación de no atribución**, no una supresión verificada. Las cifras de producción deben revisarse directamente en el entorno correspondiente antes de presentarse al auditor.
- **Cierre:** todavía no existe un camino que verifique independientemente cada área y ponga `fulfillment_complete=true` respaldado por evidencia. No implementar un atajo booleano; conservar casos abiertos o documentar no-atribución bajo sus requisitos.

API de evidencia **interna y de solo lectura** propuesta en el PR:
`GET /api/internal/shopify/privacy/cases/{request_id}/evidence-summary` con `X-Internal-Secret`.
Responde 10 estados y controles sin datos personales, permiso, ciphertext, credenciales, correo, teléfono o dominio. Requiere secreto interno y no está diseñado para entregarse directamente a revisores externos.

## 3. Evidencia externa faltante

| Superficie | Criterio de aceptación |
|---|---|
| AWS S3 + versiones | Manifest por objeto/versiones, procedencia tienda/sujeto y resultado verificable sin claves públicas |
| Amazon Bedrock + S3 Vectors | Correspondencia documento ↔ tienda/sujeto, eliminación/depuración de fragmentos y vectores derivados tras sincronización |
| Google Workspace | Distinguir fuente del comerciante de copias DIAGLOB, evitar borrar fuente ajena sin instrucción |
| Campañas y colas | Demostrar con fixtures que mensajes en vuelo, schedulers, retries y workers revisan tombstones antes del envío |
| Email/WhatsApp/Instagram/Telegram | Determinar proveedor real, datos transmitidos, solicitud y respuesta; detectar uso histórico |
| Logística y proveedores | Conservar solo registros exigidos legalmente y evidenciar acciones de supresión permitidas |
| AWS Lightsail y restauraciones | Ledger externo inmutable, prueba aislada de restauración, reconciliación antes de reabrir ingreso |

**No declarar** que un SLA, una regla S3, `dataDeletionPolicy=DELETE`, un test unitario o la mera presencia de un HMAC acredita por sí solo un borrado real en un tercero.

## 4. Preparación segura de revisión para Shopify

La documentación oficial exige **credenciales de prueba funcionales e instrucciones para la aplicación**, además de un breve video del flujo:
- https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
- https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements

### Dos caminos de auditoría (no compartir credenciales de producción)

**A. Revisor funcional de Shopify App Store**:
1. Crear o seleccionar una tienda de desarrollo Shopify **verificada**, con instalación funcional de DIAGLOB, productos/clientes/pedidos **sintéticos** y rutas de facturación en modo test.
2. Crear una organización/tenant DIAGLOB aislada para revisión, sin acceso a tiendas ni fuentes organizacionales reales; designar el merchant owner de prueba.
3. Dar al revisor el acceso que Shopify requiera por su propio canal de revisión. Si DIAGLOB requiere un login externo, generar credenciales independientes, efímeras y revocables **a través del flujo de invitación/autenticación existente**, restringidas al tenant de pruebas. Validar login y MFA antes de compartir.
4. Suministrar en el formulario de revisión de Shopify: URL de instalación, ruta de ingreso, usuario de prueba **solo por canal de revisión**, instrucciones E2E, video y cómo solicitar acceso de colaborador si hiciera falta.
5. Probar instalación, selección de plan/prueba, onboarding, Shopify OAuth, scopes y 3 webhooks con fixtures. No exponer una funcionalidad falsa de privacidad: demostrar recepción, manifest, bloqueos y evidencias, explicando los pasos que requieren revisión humana.
6. Revocar acceso de prueba al terminar y preservar un audit mínimo (sin tokens).

**B. Auditor técnico de controles**:
1. Entregar un **expediente redactado/anonimizado** con PRs, commits, CI, inventario AWS agregado y matriz de 10 áreas; nada de PII, firmas, secretos ni accesos globales.
2. Cuando se requieran verificaciones técnicas más profundas, habilitar una vía de **solo lectura en ambiente de pruebas**, con restricción temporal de acceso, aprobaciones de seguridad y logs, o preparar reportes exportados por un operador interno.
3. No compartir `DIAGLOB_INTERNAL_SECRET`, claves Paddle, API tokens, PostgreSQL ni SSH de Lightsail con Shopify. El endpoint interno no es un portal público de auditoría.

### Inventario necesario antes de crear cuentas

| Dato | Estado |
|---|---|
| Tienda Shopify de desarrollo y URL exacta | Pendiente de seleccionar/verificar |
| Tenant DIAGLOB exclusivo de demostración | Pendiente de confirmar |
| Persona/correo de recepción de la invitación del revisor | No solicitado aún por Shopify |
| Ruta de login definitiva y MFA | Pendiente de prueba |
| Video/screencast y guía E2E | Pendiente |
| Evidencias externas/legales independientes | Pendiente |
| Accesos creados y entregados | **No realizados** |

Usar siempre información auténtica de la cuenta/tienda y el canal oficial de revisión. No inventar credenciales ni publicar un password en GitHub.

## 5. Evidencia y responsabilidad documental

El informe legal que se entregue a Shopify debe presentarse como **declaración técnica/documental del representante legal**, no como dictamen de revisor fiscal independiente salvo que un profesional competente acepte el encargo, verifique pruebas originales y firme su opinión.

Para atribución del representante, identidad, facultades y calidad de representante legal, verificar documentación corporativa vigente. **No colocar número de cédula, firma, RUT ni documentos personales en este repositorio público o privado de desarrollo**; custodiar la declaración nominativa fuera de Git.

## 6. Próximo lote de implementación

- Verificación por caso: construir registro de evidencia con estado explícito `collected` / `independently_reviewed` por superficie, firma de revisor y hashes, sin permitir cambios de estado arbitrarios por API.
- Consolidación `data_request`: exportar mediante conectores con procedencia comprobada, cifrado de destino y confirmación de recepción por merchant; registrar excepción por fuente.
- `customers/redact`: limpieza de automations y vectores por cliente; no ejecutar automáticamente cuando procedencia es ambigua.
- `shop/redact`: ejecución de KB exclusivas, inventario de compartidas, proveedores, archivos, colas; impedir completado cuando quedan dependencias.
- Restauración: anclaje externo WORM (independiente del backup de la BD) y ejercicio de restore aislado.
- Cuenta de revisión: crear solo cuando consten tienda, tenant y canal autorizado; verificar antes de compartir.
