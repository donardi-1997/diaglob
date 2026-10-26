# Reporte de correcciones — 26 de octubre de 2026

## Alcance y estado del repositorio

- Directorio de trabajo: `C:\Users\adria\OneDrive\Documentos\diaglob`.
- Sincronización: `git pull --ff-only origin main`, terminado correctamente en `6664cfc`.
- Se conservaron los archivos locales no versionados existentes: `.agents/`, `skills-lock.json` y los dos documentos de autoevaluación de Shopify.
- Cambios locales, todavía sin commit, push ni despliegue. No se usaron credenciales ni servicios de producción.
- Sin modificaciones a modelos, migraciones, `backend/app/main.py` ni al motor de aprovisionamiento Knowledge.

## Correcciones implementadas

| Hallazgo | Corrección | Cobertura |
| --- | --- | --- |
| Pagos: `TypeError` después de operar con el proveedor | Se pasa la sesión `db` al actualizar el estado tras crear, reconciliar, cancelar o devolver un pago. | Resultados exitosos de los cuatro flujos, con proveedor simulado. |
| Pago inferior al total del pedido | Importe y moneda provienen del pedido. Un recibo pagado solo liquida el pedido si coinciden organización, tienda, moneda e importe completo. | Entrada manipulada, importe omitido, pagos heredados insuficientes y liquidación correcta. |
| Estados Nequi falsificables mediante webhook | Toda notificación consulta el estado al proveedor; nunca se usan su estado ni su fecha como autoridad. Un fallo de consulta devuelve HTTP 503 sin consumir el evento. | Estados falsificados, caída del proveedor, reenvíos y fecha manipulada. |
| Acceso a tiendas no asignadas | Dependencia de autorización compartida en las 18 rutas de pagos, Telegram y posventa. El envío Telegram valida la tienda real de la conversación. | Miembro restringido, otra organización, tienda eliminada y acceso autorizado. |
| Acceso inconsistente a Knowledge | Política de dominio y dependencia común en las 16 rutas dirigidas a una KB, incluidas fuentes, sincronización e ingestión. El listado usa la misma política de visibilidad. | KB invisible, otra organización, acceso permitido y bases compartidas. |

### Endurecimiento relacionado

- Un reintento de un pago con referencia del proveedor devuelve la transacción existente, sin repetir la llamada de creación.
- Una clave de idempotencia no puede reutilizarse para otra tienda, pedido, proveedor, importe, moneda, teléfono o método de pago.
- Se rechazan importes no finitos (`NaN` e infinitos).
- Se valida la estructura de los webhooks antes de consultar SQL; listas, objetos usados como ID y otros JSON inválidos devuelven error controlado.
- Los errores del proveedor ya no se devuelven como texto crudo en las respuestas de estas operaciones de pago.

### Decisión de permisos en bases compartidas

Se conserva la lectura de conocimiento compartido y de ámbito organizacional. Un miembro restringido no puede modificar contenido que afecta a tiendas fuera de su asignación: para una KB compartida necesita acceso a todas sus tiendas; para una KB organizacional se conserva el requisito de acceso global o propietario.

## Archivos principales

- `backend/app/services/payment_service.py`
- `backend/app/payments/nequi.py`
- `backend/app/api/payments.py`
- `backend/app/api/store_access.py`
- `backend/app/api/telegram.py`
- `backend/app/api/post_sales.py`
- `backend/app/services/knowledge_bases.py`
- `backend/app/api/knowledge_access.py` (nuevo)
- `backend/app/api/knowledge.py`
- `backend/tests/test_payments.py`
- `backend/tests/test_store_authorization_regressions.py` (nuevo)

## Validación

| Comprobación | Resultado disponible |
| --- | --- |
| Pagos: `python -m pytest tests/test_payments.py -q` | 64 pruebas correctas. |
| Autorización, arquitectura y contrato de rutas (repetición final) | 239 pruebas correctas. Junto con pagos: 303 pruebas enfocadas correctas sobre la versión actual. |
| Validación enfocada inicial de ocho archivos | 354 correctas y cinco fallos al conservar metadatos cuando el estado no cambiaba; se corrigió la causa y las cinco regresiones pasaron en la repetición de pagos. |
| Nuevas pruebas | 30 casos de pagos y 104 de autorización HTTP; total: 134 regresiones adicionales. |
| Auditoría de dependencias de autorización | 16 rutas Knowledge, nueve pagos, tres Telegram, seis posventa y un envío por conversación: ninguna sin protección. |
| Ruff: `ruff check app/ tests/ tools/` | Correcto. |
| Importación de `app.main` | Correcta. |
| `git diff --check` | Correcto; Git solo avisa de normalización LF/CRLF en Windows. |
| Frontend: `npm test` | 141 pruebas correctas. |
| Frontend: `npm run build` | Correcto; conserva advertencias de tamaño de bundle e importación dinámica inefectiva. |
| Frontend: `npm run lint` | Cero errores; 172 advertencias preexistentes. No se cambiaron reglas. |
| Suite completa de backend | Terminada: **2892 correctas, 2 fallos** en 2144,14 s. Ambos fallos Windows corresponden al bootstrap de secretos Shopify (`os.fchmod` no disponible y symlink sin privilegios). Se corrigieron en la revisión Shopify posterior y pasaron en la selección enfocada; no se repitió toda la suite después. |

Las pruebas usan SQLite de prueba/en memoria, credenciales AWS ficticias, reconciliación de inicio desactivada y proveedores simulados. El intérprete aislado tiene instaladas las versiones de `backend/requirements.txt`; no se sustituyó el entorno virtual local del usuario. Entorno local: Windows, Python 3.12.10 y Node 24.20.0; CI utiliza Ubuntu y Python 3.11, por lo que esta validación no equivale a una ejecución de CI.

La comprobación enfocada ejecutó:

```text
python -m pytest -q --tb=short --disable-warnings
  tests/test_payments.py tests/test_store_authorization_regressions.py
  tests/test_post_sales.py tests/test_telegram.py tests/test_telegram_delivery.py
  tests/test_bedrock_knowledge_base.py tests/test_google_sheets.py
  tests/test_shopify_path_store_membership.py
```

La suite completa se lanzó con `python -m pytest -q --tb=short --disable-warnings` y un reporte JUnit fuera del repositorio, en `C:\Users\adria\AppData\Local\Temp\opencode\diaglob-backend-full.xml`.

Las correcciones de este reporte quedaron incorporadas posteriormente en `3930472`. La revisión específica de Shopify y sus cambios locales posteriores se documentan por separado en [Shopify: revisión y correcciones — 2026-10-26](shopify-review-remediation-2026-10-26.md); no confundir sus selecciones enfocadas con una repetición completa de todos los dominios.

## Pendientes y límites

1. Revisar, con autorización operativa independiente, pagos históricos: el cambio evita nuevas liquidaciones incorrectas, pero no reescribe transacciones ni pedidos existentes en producción.
2. Verificar los flujos reales en sandbox/staging de Nequi y Mercado Pago antes del despliegue. Esta sesión no genera cargos ni devoluciones reales.
3. La durabilidad ante caídas del proceso entre la respuesta del proveedor y el commit, la concurrencia de solicitudes y la persistencia del QR requieren una revisión transaccional adicional. No se promete procesamiento exactamente una vez.
4. No se ha añadido soporte nuevo de webhooks de Mercado Pago: se conserva la capacidad declarada por su adaptador.
5. La deuda previa del frontend (advertencias de lint y tamaño de bundles) no se elimina mediante desactivación de reglas ni una refactorización masiva ajena a estos fallos.
6. No es una auditoría completa de todas las integraciones y rutas del repositorio.
