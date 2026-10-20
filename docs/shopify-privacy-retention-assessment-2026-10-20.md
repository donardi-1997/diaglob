# DIAGLOB — Evaluación técnica de conservación de datos

**Alcance:** propuesta de política y controles de revisión para información de compradores y tiendas Shopify. **No es una política legal aprobada, no ejecuta exportaciones o borrados y no modifica datos de producción.**

## Flujo disponible

1. Recuperar la plantilla: `GET /api/internal/shopify/privacy/retention/template`, con `X-Internal-Secret`.
2. Recopilar en un repositorio seguro y controlado evidencias aprobables de finalidad, base jurídica, jurisdicción, plazos de cada clase de información, inicio del cómputo, excepciones legales, retención mínima, procesadores y restauración. Evitar cualquier selector o dato personal dentro de la petición de evaluación.
3. Preparar una propuesta estructurada con las **seis categorías** de `RETENTION_CONTROLS`.
4. Evaluar las **brechas técnicas** mediante `POST /api/internal/shopify/privacy/retention/assess`.
5. Corregir cada brecha reportada. Aunque las referencias estén presentes, **la propuesta nunca se aprueba automáticamente**: falta verificación jurídica independiente, trazabilidad firmada, límites de alcance por tienda/cliente, proveedores y garantías operativas de supresión y restore.

### API del evaluador

Encabezados: `X-Internal-Secret: (valor secreto)`, `Content-Type: application/json`. Máximo **16 KiB**; autenticación previa a la lectura del cuerpo y errores genéricos para evitar reflejar contenido accidentalmente sensible. No escribir el secreto ni las referencias en URL o logs.

Ejemplo exclusivamente **sintético**:

```json
{
  "schema_version": 1,
  "categories": [
    {
      "category": "customer_contact",
      "jurisdiction": "CO",
      "retention_days": 30,
      "retention_start_event": "collection",
      "statutory_exception": "not_reviewed",
      "legal_hold": "not_reviewed",
      "disposition": "undecided"
    }
  ]
}
```

El valor `30` de este ejemplo es ficticio y **no constituye una propuesta de plazo ni una regla legal**. La API permite un plazo expresado en días dentro de límites técnicos, **sin validar su fundamento jurídico**. Nunca reutilizar la ventana de respuesta de Shopify como período de retención por defecto.

Otros campos opcionales son los digests SHA-256 de documentos de finalidad, base jurídica, evento de inicio excepcional, excepción legal, legal hold, minimización, terceros, backups y visto bueno. Se aceptan únicamente hashes hexadecimales y códigos definidos; no texto libre ni datos personales. Cada digest significa **referencia declarada**, no comprobante validado.

### Garantías de fallo seguro

- Se rechazan categorías desconocidas, repetidas, periodos fuera de rango y campos adicionales.
- Una categoría ausente mantiene el código `RETENTION_CATEGORY_DRAFT_MISSING`.
- Un legal hold activo conserva `LEGAL_HOLD_ACTIVE_NO_ERASURE_AUTHORIZATION`; sin revisión conserva `LEGAL_HOLD_NOT_REVIEWED`.
- Aun con seis categorías completas y digests presentes, `INDEPENDENT_LEGAL_APPROVAL_NOT_VERIFIED` y `LIVE_ERASURE_WORKFLOW_NOT_AUTHORIZED` siguen bloqueando el proceso.
- La respuesta devuelve solo nombres de categorías y **códigos de brecha**; no refleja hashes, jurisdicciones, plazos propuestos ni contenido recibido.
- `policy_approved=false`, `live_export_authorized=false`, `live_erasure_authorized=false`, `fulfillment_complete=false` en todas las respuestas válidas.

### Pruebas

```bash
cd backend
pytest -q tests/test_shopify_privacy_retention_assessment.py tests/test_shopify_privacy_inventory_report.py tests/test_route_contract.py
```

### Para cerrar realmente este frente

- Jurídico, finanzas y seguridad deben revisar fundamentos, duración, jurisdicciones, excepciones, minimización y retención obligatoria por categoría.
- Acordar el diseño de firma y validación **independiente** de esos documentos, con identidad de revisor, revocación, versionado, vigencia y auditoría.
- Aplicar las decisiones aprobadas a cada fuente (incluidas tablas compartidas, colas, terceros, respaldos y restauraciones), con controles técnicos probados antes de habilitar ejecución.
- Ensayar supresiones de cliente y tienda en fixtures sintéticos con datos de dos tiendas y casos de legal hold; no probar datos productivos sin autorización.

**Este PR añade un evaluador de propuestas**, no una herramienta de aprobación jurídica ni un botón de borrar.
