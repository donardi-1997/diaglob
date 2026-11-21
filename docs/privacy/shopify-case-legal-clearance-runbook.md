# Shopify `customers/redact` — revisión jurídica independiente por caso

> **Implementación de seguridad, NO autorización jurídica.** Ningún dato de comprador debe eliminarse en producción por el mero hecho de crear una firma o adjuntar un hash. Todas las aprobaciones deben provenir de un revisor realmente autorizado y de documentos auténticos guardados fuera del repositorio.

## Problema corregido

Antes, el permiso del operador `local_redaction` contenía `legal_hold=false` emitido por el propio firmante técnico, sin segunda firma por caso. Un operador con una clave de ejecución podía afirmar la ausencia de retención legal sin acreditar revisión independiente.

Ahora, además del permiso `X-Privacy-Execution-Permit`, el endpoint `POST /api/stores/{store_id}/shopify/privacy/cases/{request_id}/local-redaction` exige `X-Privacy-Legal-Clearance`: una autorización **Ed25519 firmada por un revisor independiente**, vinculada al `request_id`, organización, tienda, `scope_sha256`, `policy_sha256`, dos hashes de evidencia y `legal_hold=false`, con vigencia inferior a 24 horas.

La nueva variable de producción `SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY` debe contener **solo la clave pública** del revisor legal, diferente de `SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY`. Sin ambas claves distintas, el endpoint falla de forma cerrada y `redaction_enabled=false` en la autoevaluación operativa. La clave privada **nunca** se instala en DIAGLOB ni se sube a CI/GitHub.

## Flujo autorizado y segregación de funciones

1. **Recepción y evaluación:** se requiere webhook HMAC válido, tienda verificada, `customer.id` y `orders_to_redact` comprobados. Consultar el preview del caso con una cuenta owner. Obtener su `scope_sha256` y `planned_restore_checkpoint`.
2. **Instrucción auténtica del comerciante:** el responsable del tratamiento o autoridad aplicable documenta la instrucción para el mismo caso y la misma tienda. Guardar su evidencia en ubicación restringida.
3. **Revisión jurídica independiente:** un revisor distinto del firmante técnico verifica la política aprobada, jurisdicción, retenciones por categoría, litigios, bloqueos legales y excepciones. Guardar acta atribuible al caso y limitarla al alcance aprobado.
4. **Firma legal:** el revisor autorizado crea el documento de clearance con su clave **fuera del servidor**; debe indicar expresamente `--legal-hold-cleared` después de comprobarlo. Si existe bloqueo o duda, **no firmar**. Un bloqueo parcial requiere procedimiento más granular antes de autorizar eliminación de esos campos.
5. **Anclaje externo:** registrar de forma segura el checkpoint/tombstones fuera del mismo backup y cargar los valores de comparación desde el ledger independiente. Un valor dentro de la BD restaurada no es evidencia externa.
6. **Firma técnica:** el operador con **otra clave** firma su `local_redaction` para el mismo `scope_sha256`, tienda, caso y checkpoint, con TTL inferior a 24 h.
7. **Ejecución controlada:** presentar ambos headers solo por un canal autenticado. El servicio vuelve a verificar alcance, política, rol owner, fechas, dos firmas y checkpoint antes de modificar registros locales.
8. **Verificación:** el resultado de redacción local mantiene `fulfillment_complete=false`; faltan comprobaciones separadas sobre IA, archivos, colas, proveedores y restauraciones. No afirmar cumplimiento de Shopify por la sola respuesta 200.

## CLI del revisor (solo estación aprobada)

Desde la carpeta `backend`:

```bash
python -m tools.shopify_privacy_legal_clearance keygen --out /private/diaglob-legal
```

La salida contiene `SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY`. Instalar únicamente esta **clave pública** como configuración segura del backend, previa revisión de la política y con independencia del permiso técnico.

Después de revisar originales y obtener el scope exacto:

```bash
python -m tools.shopify_privacy_legal_clearance sign \
  --key /private/diaglob-legal/clearance.key \
  --request-id <id-opaco-64-hex> \
  --organization-id <org> --store-id <tienda> \
  --scope-sha256 <sha256-del-preview> \
  --merchant-instruction /private/evidence/merchant-instruction.pdf \
  --legal-review /private/evidence/legal-case-clearance.pdf \
  --reviewer-role privacy_counsel \
  --legal-hold-cleared \
  --ttl-minutes 60
```

El CLI calcula SHA-256 de ambos documentos sin enviarlos al servidor y devuelve una credencial de duración limitada. Custodiarla como un token bearer, sin publicarla en tickets, shell history compartida, commits, logs de CI ni chat. Los roles aceptados son `privacy_counsel`, `merchant_controller` y `authorized_privacy_reviewer`, pero escribir un nombre de rol no reemplaza la acreditación real de facultades.

Para ejecutar desde una cuenta owner autenticada, enviar ambos valores mediante encabezados `X-Privacy-Execution-Permit` y `X-Privacy-Legal-Clearance`. No enviar permisos por querystring ni incrustarlos en registros de auditoría.

## Qué verifica y qué NO verifica el código

**Verifica:** firma Ed25519 independiente, claves distintas, legitimidad de alcance técnico por hash, categoría `legal_hold=false` explícita y no coercible, periodo menor de 24 h, política vigente y hashes de dos artefactos de evidencia firmados.

**No verifica automáticamente:** verdad de un acta, facultades legales reales del firmante, idoneidad de la norma jurídica, existencia histórica de todos los holds, que las evidencias provengan del comerciante correcto, eliminación en terceros o supresión de datos en backups. Eso exige controles organizativos, registros privados, revisión humana y pruebas de infraestructura.

## Seguridad, despliegue y compatibilidad

- Este cambio endurece las peticiones **nuevas y los reintentos** de `local_redaction`: sin segundo permiso, ahora fallan con código de error opaco; las exportaciones `local_export` no se modifican.
- No activar el processing de producción hasta tener una política aprobada, nombramiento del revisor, claves separadas, custodia de evidencias y ledger externo.
- Aunque el backend exponga `redaction_enabled`, esta bandera solo comprueba configuración. No representa la aceptación del caso ni la entrega final a Shopify.
- No fusionar ni desplegar sin CI, revisión de seguridad independiente y pruebas sintéticas de tienda compartida, firma inválida, hold activo, vencimiento, ID de tienda diferente y rollback.
- Documento complementario de política propuesta: `docs/privacy/shopify-customers-redact-legal-approval-draft-2026-11-20.md` (en PR documental independiente hasta ser fusionado).

## Pruebas sintéticas

```bash
cd backend
pytest -q tests/test_shopify_privacy_local_execution.py tests/test_shopify_privacy_attestations.py tests/test_shopify_privacy_permit_tool.py
```

Ninguna prueba crea un permiso legal real ni ejecuta eliminación de datos de compradores en producción.
