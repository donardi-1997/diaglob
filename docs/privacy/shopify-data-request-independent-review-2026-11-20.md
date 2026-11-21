# customers/data_request — revisión independiente antes de exportar PII

> **Control técnico, no aprobación legal ni cumplimiento completo.** Todos los datos y actas reales deben permanecer en una bóveda privada con revisión autorizada.

## Brecha que se cierra

Antes el flujo `local_export` exigía únicamente un permiso Ed25519 técnico de alcance exacto con `legal_hold=false`. No requería que un revisor jurídico o controlador del comercio confirmara documentalmente la finalidad de entrega, límites de retención y ausencia de bloqueos aplicables. No se debe interpretar la firma de un operador técnico como aprobación jurídica.

La ruta `POST /api/stores/{store_id}/shopify/privacy/cases/{request_id}/local-export` requiere ahora **dos** encabezados independientes:

- `X-Privacy-Execution-Permit`: permiso técnico de `local_export`, emitido por el operador, TTL inferior a 24h, ligado a solicitud, organización, tienda, política y `scope_sha256`.
- `X-Privacy-Legal-Clearance`: autorización del revisor independiente, misma solicitud, organización, tienda, política y `scope_sha256`, más hashes de la instrucción del comerciante y la decisión jurídica de alcance/retención, TTL inferior a 24h.

El servidor comprueba ambas firmas, el owner autenticado, correspondencia exacta tienda/cliente/pedidos, y la política vigente **antes** de llamar al extractor que contiene datos del comprador.

Si falta cualquiera de los dos permisos, su firma es inválida, el alcance difiere o la política ha cambiado, el flujo falla cerrado. `export_enabled` del auditor ahora requiere que exista configuración de clave pública legal independiente, adicional a permiso técnico/política; esto sigue siendo *readiness de configuración*, no aprobación de un caso.

## Entrega y cierre siguen parciales

La exportación mantiene `complete=false` y `fulfillment_complete=false`. El archivo cifrado/ticket de acceso se expide únicamente para el merchant owner autenticado con acceso de un solo uso y caducidad. La protección no certifica cobertura de conocimiento/IA, colas, archivos externos, procesadores, confirmación completa de entrega y excepciones jurídicas. **No cerrar automáticamente la solicitud.**

No cambiar el comportamiento de `shop/redact` ni iniciar exportaciones reales de clientes hasta que el revisor asignado valide los documentos y se habiliten controles tras staging/CI.

## Evidencia exigida y prueba

- Instrucción real del responsable/merchant para el caso exacto.
- Revisión jurídica comprobada de retención, acceso, confidencialidad, legal holds y jurisdicción.
- Firmas privadas separadas (operador y revisor) y TTL corto; almacenar solo claves públicas en runtime.
- Pruebas sintéticas de ausencia de permiso, cambio de tienda, hold activo, firma inválida, single-use, aislamiento multi-tenant y no creación de artefactos tras rechazo.
- Registro PII-free para cada ejecución y reintento; evidencia independiente de entrega completa pendiente.

Comando de test:
```bash
cd backend
pytest -q tests/test_shopify_privacy_local_execution.py tests/test_shopify_privacy_attestations.py tests/test_shopify_privacy_legal_clearance.py
```

**Nota legal:** una firma que refiere a documentos no prueba la validez sustantiva de esos documentos; la decisión real sigue siendo responsabilidad del comerciante, del revisor autorizado y del responsable de DIAGLOB según sus roles legales aplicables.
