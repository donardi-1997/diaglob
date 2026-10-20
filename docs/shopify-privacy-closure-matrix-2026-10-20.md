# DIAGLOB — Cierre de privacidad Shopify (20 oct 2026)

**Estado:** diagnóstico técnico y criterios de aceptación; **NO autoriza exportación ni borrado en producción**.
**Ámbito:** app Shopify existente + datos de DIAGLOB que puedan corresponder a un comprador o tienda Shopify. Aplica a solicitudes de acceso y supresión; no confundir desinstalación, desactivación ni borrado lógico con `shop/redact`.
**Fuentes revisadas:** `shopify.app.toml`, `backend/app/api/shopify.py`, `backend/app/api/stores.py`, `backend/app/services/shopify_compliance_webhooks.py`, `backend/app/services/shopify_privacy_*.py`, `backend/app/shopify_privacy_operational_audit.py`.
**Regla:** nunca reportar `PASS` o `fulfilled` a partir de un HTTP 200, una cola de trabajos, un manifiesto, una entrega sintética o un inventario.

## 1. Inventario de información — pendiente de cobertura campo por campo

El inventario de metadatos existe en `shopify_privacy_inventory_coverage.py`; es **parcial**, no una certificación. Para cada entidad completar: categoría personal/no personal, origen, finalidad/base jurídica, `organization_id` + `store_id` + Shopify `shop_id`, propiedad compartida, identificador de cliente original, réplica/archivo/cola, proveedor, responsable, ubicación, plazo de retención, operación de exportación, operación de supresión y prueba.

| Superficie | Referencias conocidas | Brecha y criterio de aceptación |
| --- | --- | --- |
| Clientes y perfiles | `customers`, `customer_store_profiles` | Confirmar identidad del sujeto por ID externo firmado; no borrar el cliente compartido si pertenece a otra tienda; cerrar fuentes huérfanas y variantes de ID. |
| Pedidos y cobros | `orders`, `order_items`, checkouts, proveedores de pago | Separar PII de asientos financieros sujetos a conservación; preservar integridad de referencias y minimizar datos no obligatorios. |
| Conversaciones, mensajes y archivos | `conversations`, `messages`, conocimiento, adjuntos y almacenamiento objeto | Incluir cuerpo, anexos, prompts, resultados derivados, embeddings e índices; eliminar referencias y copias relacionadas cuando proceda. |
| IA y agentes | `agent_chat_sessions`, `agent_chat_messages`, `agent_chat_tool_calls`, `agent_action_approvals` | Verificar atribución por tienda/sujeto, histórico de herramientas y terceros; no usar coincidencias de email como única prueba de identidad. |
| Automatización | campañas, audiencias, ejecuciones, entregas, flujos, reintentos, dead-letter | Cubrir datos en ejecución, payloads y destinatarios; cortar futuras entregas, reintentos y reingestas tras supresión. |
| Riesgo y derivados | `customer_risk_reports`, `customer_risk_disputes`, analítica | Revisar información inferida y datos copiados sin FK directo al comprador. |
| Logística y proveedores | pedidos, envíos, tracking, CJ, Dropi y mensajería | Inventariar solicitudes exportadas al tercero y su mecanismo comprobable de supresión. |
| Logs, auditoría y copias | aplicación, observabilidad, DB, objetos, respaldos | Evitar PII en eventos nuevos; decidir minimización, plazos, retención justificada y reconciliación post-restore. |

**Evidencia exigida:** exportar inventario de esquema desde metadata, relacionar columna → sujeto → tienda para cada tabla sensible, revisar campos JSON/texto libre, escanear buckets y colas, y justificar las excepciones. `unclassified_sensitive_tables` y fuentes externas sin clasificar deben impedir el visto bueno.

## 2. Política de conservación — sin plazos arbitrarios

La definición técnica actual (`shopify_privacy_controls.RETENTION_CONTROLS`) contempla:
- contacto del cliente;
- pedidos y contabilidad;
- entregas y devoluciones;
- conversaciones y adjuntos;
- automatizaciones e IA;
- logs y evidencia de auditoría.

**Decisión obligatoria por categoría y jurisdicción:** finalidad; responsable; base de legitimación; plazo exacto y evento de inicio; obligación fiscal/contable; excepciones y legal hold; minimización y seudonimización; acceso restringido; borrado vencido; tercero afectado; evidencia de aprobación jurídica. Ningún plazo de conservación se deduce automáticamente de un país. Los `SHOPIFY_PRIVACY_*_KEY`, hashes HMAC de tombstones y tickets cifrados también requieren política de conservación y rotación.

**Plazo operativo Shopify:** reconocer solicitudes válidas con 2xx y completar la acción dentro de **30 días tras recibirlas**, salvo retención legalmente exigida. Los webhooks de `shop/redact` llegan, normalmente, **48 h tras desinstalar**. La fecha de recepción se registra; no iniciar el reloj cuando un operador abra el caso. Fuente: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance .

**Evidencia exigida:** matriz aprobada por responsables jurídico, financiero, seguridad y operaciones, con decisiones aplicadas a código/SQL y versiones vigentes.

## 3. Webhooks e idempotencia

**Ya existe:** `shopify.app.toml` declara `customers/data_request`, `customers/redact` y `shop/redact` sobre un destino HTTPS; `shopify.py` autentica HMAC y limita el cuerpo; `shopify_compliance_webhooks.py` persiste un recibo cifrado, deduplica por ID de entrega, verifica coherencia del contenido y genera tareas en la misma transacción. Esto **no verifica la versión activa de Shopify**.

**Aceptar solo tras comprobar:**
1. Configuración en **versión liberada** de la **app existente** del Shopify Dev Dashboard, sin crear una segunda aplicación ni cambiar scopes accidentalmente.
2. HTTP 401 para HMAC ausente/inválido en cada tema; JSON válido con autenticación aceptado y recibo transaccional antes del 2xx.
3. Repetición de un delivery ID idéntico: un solo recibo y cola; ID reutilizado con payload contradictorio: conflicto y señal operativa; concurrencia y caídas de DB: reintentos sin pérdida.
4. Webhook tardío después de desinstalación: alcance resuelto por identidad histórica verificada; casos desconocidos permanecen pendientes, jamás ligados al primer dominio parecido.
5. Pruebas de carga/latencia, observabilidad sin PII y escalamientos de solicitudes próximas a vencer.

**No realizar pruebas con callbacks falsos firmados sobre la base de producción.** Shopify CLI `webhook trigger` prueba el transporte, no la suscripción activa.

## 4. Exportación segura de datos

**Estado real:** `shopify_privacy_local_processor.py` solo genera un snapshot local parcial cifrado en memoria; `shopify_privacy_secure_delivery.py` permite únicamente tickets/artefactos **sintéticos**, y los bloquea contra DB de producción. No anunciar exportación de compradores habilitada.

**Para permitir datos reales:** cobertura completa, identidad tienda/sujeto inequívoca, autenticación del comerciante, destinatario autorizado, manifest versionado, normalización de datos, cifrado autenticado, entrega exclusiva para solicitud + destinatario + tienda, ticket de uso único y TTL breve, revocación, borrado de artefactos al expirar, confirmación auditada de entrega, sin URLs con tokens ni archivos en logs.

## 5. Borrado de clientes

**Estado real:** alcance, previsualización, manifiestos y supresiones preparadas; no hay mutación productiva aprobada.

**Implementación requerida:** identidad exacta del `customer.id` por tienda, inventario de claves externas y registros derivados, retención legal antes de transacción, supresión/anominización por categoría, manejo explícito de clientes compartidos, cancelación de colas y flujos, borrado/solicitud a subprocesadores, tombstones activos que bloqueen reingesta, verificación posterior sin PII, reversión/fallo seguro sin declarar éxito parcial como terminado.

**Evidencia exigida:** tests E2E sintéticos de cliente en dos tiendas, pedidos contables preservados sin PII innecesaria, enlaces huérfanos, reintentos, backup restore y proveedor que falla.

## 6. Borrado de tiendas

**Hallazgo verificable:** `DELETE /api/stores/{store_id}` únicamente marca `active=False` y `deleted=True`. Esto es baja administrativa; no equivale a `shop/redact`.

**Implementación requerida:** flujo de cierre después del webhook firmado, tenant y shop ID históricos verificados, inventario de dependencias por tienda, separación de clientes compartidos y datos fiscales conservables, limpieza de integración/OAuth/colas/objetos/secretos, coordinación de proveedores, mantenimiento mínimo de evidencia de cierre sin PII, y bloqueo de reingesta y restauración. Un `shop/redact` de tienda A nunca toca tienda B del mismo tenant.

## 7. Proveedores y respaldos

Los controles declarados incluyen WhatsApp, Instagram, email, CJ, Dropi, Meta, AWS Bedrock, archivos/objetos; y colas, replays, DB, object storage, restore y tombstones. La presencia de un control **no demuestra** una supresión.

**Por proveedor:** contrato/DPA, regiones, propósito y categorías de PII, cadena de subprocesadores, política propia de retención, API/canal de borrado, referencia verificable sin exponer datos del comprador, plazo, retry, prueba de cumplimiento y escalamiento. **Respaldos:** registro de TTL, cifrado, acceso, expiración natural, restauración controlada y re-aplicación de tombstones antes de habilitar servicios/eventos. No prometer borrado físico inmediato de backups inmutables sin capacidad demostrada.

## 8. Auditoría y pruebas — evidencia de cierre

La auditoría existente es **agregada y sin PII**, y verifica presencia de claves, recibos y diez tareas por solicitud; **no** demuestra suscripciones liberadas ni cumplimiento. Desde este PR, el informe también declara `privacy_fulfillment_release_ready=false` con los bloqueos principales, aunque el indicador independiente de salud de recepción `review_required` sea `false`.

| Escenario de prueba | Resultado mínimo antes de liberar |
| --- | --- |
| HMAC inválido y omitido en los tres temas | 401, sin escritura, sin log del cuerpo |
| Envío válido, duplicado y entrega concurrente | Un recibo, tareas consistentes, respuesta reintentable ante falla de BD |
| Tienda desvinculada y webhooks tardíos | Caso persistido, sin reasignación de tenant por conjetura |
| Exportación del cliente A en tienda X | Solo datos atribuibles a A/X, completos, cifrados, sin referencia a B |
| Descarga repetida/expirada/revocada | No expone datos; ticket de un uso |
| Supresión cliente compartido A entre X/Y | X suprimida, Y preservada conforme a obligaciones |
| Supresión completa de tienda X | Ninguna operación sobre Y, OAuth/colas/objetos/terceros tratados |
| Reingesta después de supresión | Bloqueada por tombstone validado |
| Retención por obligación jurídica | Datos mínimos restringidos, resto suprimido, excepción documentada |
| Restablecimiento desde backup | Reconciliación de supresiones **antes** de reactivar mensajes/importadores |
| Proveedor rechaza borrado | Caso queda abierto con alerta y reintento, no falso estado completo |
| Revisión final | Evidencias por solicitud, aprobadores independientes, sin PII en observabilidad |

### Orden de ejecución y puertas de salida

1. **Inventario** — cerrar campos y superficies externas; responsable: ingeniería/datos. **Bloquea** toda eliminación o exportación real.
2. **Retención** — aprobar política, excepciones y terceros por jurisdicción; responsable: legal/finanzas/seguridad.
3. **Transporte** — corroborar versión activa Shopify y HMAC real, y probar idempotencia/concurrencia con fixtures.
4. **Datos de acceso** — construir exportación completa y canal de entrega real, sin reutilizar la habilitación sintética de producción.
5. **Supresión cliente y tienda** — ejecutar solo con alcance validado, política, tombstones, fuentes externas, evidencias y controles independientes.
6. **Respaldos/proveedores** — procedimientos verificables y restore drills; revalidar cierres previos.
7. **Auditoría** — pruebas E2E, security review, revisión jurídica, revisión App Store y go/no-go explícito.

**Estado de cierre a 2026-10-20:** ninguno de los ocho controles se considera completamente aprobado para datos reales. Los componentes de recepción, revisión y simulación son avances técnicos; no se declara cumplimiento ni se habilita mutación productiva.

## Comandos de validación aislada

```bash
cd backend
pytest -q tests/test_shopify_privacy_operational_audit.py
pytest -q tests/test_shopify_privacy_secure_delivery.py tests/test_shopify_privacy_synthetic_export.py
```

**Nota de ejecución:** este documento y los cambios de auditoría se prepararon por revisión remota de código; las pruebas del PR deben ejecutarse en CI antes de fusionar. No hay comprobación ejecutada de la configuración activa del Dev Dashboard ni de datos reales.
