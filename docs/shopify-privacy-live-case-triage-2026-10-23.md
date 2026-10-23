# Resolución de una solicitud Shopify shop/redact sin identidad verificada

**Fecha:** 2026-10-23. **Estado:** investigación y revisión de procedencia, no borrado completado. **P0 #266**.

Una solicitud `shop/redact` exige borrar datos de una tienda tras su desinstalación, salvo conservación legal obligatoria. Shopify la envía al menos 48 horas después del uninstall y no la envía si la app se reinstala durante la ventana. Referencia oficial: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance .

## Diagnóstico sin exponer identificadores

En el servidor de producción, como operador autorizado, ejecutar:

```bash
sudo bash -c 'set -a; source /etc/diaglob/diaglob.env; set +a; cd /opt/diaglob/app/backend; .venv/bin/python -m app.shopify_privacy_case_live_diagnostic'
```

La salida JSON presenta contadores y códigos fijos; nunca muestra Shopify shop ID, dominio, request ID, direcciones, selectores, emails ni tokens. El comando no cambia registros, no desencripta selectores, no marca tareas completas y no ejecuta eliminación. Si no se ha desplegado el módulo todavía, esperarlo por CI/deploy y no repetir con scripts copiados parcialmente.

Si `eligible_for_controlled_identity_repair=1`: hay un historial de identidad firmada con `shop_id` + dominio exactos, desinstalación previa de 48h, HMAC auditoría de recepción, cola completa y tenant/store existente sin conflictos. Un operador autorizado puede examinar la solicitud por API interna privada y valorar la operación `repair-identity`; no autoriza GDPR erasure.

Si `SIGNED_SHOP_HISTORY_MISSING=1`, `SIGNED_SHOP_HISTORY_UNVERIFIED=1` u otro código: **no adivinar tenant ni borrar la tienda POC**. Investigar manualmente Shopify Dev Dashboard, la versión activa y los registros de desinstalación/entrega real. HMAC autenticado demuestra conocimiento de clave de firma, pero el recibo interno no acredita de manera independiente origen Shopify ni determina tienda. La identidad del request debe reconstruirse de evidencia anterior, nunca fabricarse.

## Habilitar revisión autenticada (operador autorizado)

El script ya fusionado `scripts/enable-shopify-privacy-review.sh` configura `DIAGLOB_INTERNAL_SECRET` aleatorio y reinicia API solo después de un backup y comprobación de readiness. Un operador debe aprobar su ejecución y proteger la credencial: nunca compartir token, id de recibo ni JSON de clientes en GitHub issues, CI o chat.

```bash
sudo bash /opt/diaglob/app/scripts/enable-shopify-privacy-review.sh
```

Salida esperada: `REVIEW_INTERNAL_AUTH_ENABLED=true` y `PRIVACY_ERASURE_AUTHORIZED=false`. Esta habilitación **no** concede permiso de borrar. Revisar fallo/rollback antes de intentar más operaciones. El monitor continuará notificando casos abiertos.

## Condiciones antes de considerar atendido shop/redact

1. Fuente Shopify auténtica, fecha de entrega, shop ID y desinstalación verificadas; asignación única a organización/tienda.
2. Inventario y alcance completo de datos vinculados a esa tienda, incluyendo clientes compartidos, chats, automatizaciones, pedidos y archivos; nunca borrar recursos de otro tenant.
3. Política legal de retención y holds aprobada con jurisdicción, caso y responsable. Conservación obligatoria prevalece donde corresponda.
4. Plan y evidencia de borrado o anonimización en la BD, almacenamiento S3 (incluidas versiones antiguas), colas, logs, proveedores y backups/restore con barreras de reingesta.
5. Control cruzado posterior al tratamiento, auditoría de acciones y demostración de ausencia de PII activa fuera de excepciones aprobadas.
6. Solo entonces constancia de cumplimiento. `received`, `processing_prepared`, `shop_identity_recovered`, `CI success` y `Telegram delivered` no son cumplimiento.

El código mantiene `fulfillment_complete=false` en el diagnóstico; ningún script de este runbook autoriza borrado.

**Shopify App Store sigue en NO-GO para privacidad operativa mientras estas verificaciones no estén completas.**
