"""Dedicated public entrypoint for Shopify embedded App Home.

No tenant data, Shopify Admin API token or Cognito session is exposed here.
Shopify ID-token validation is implemented separately before protected features.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..services.shopify_embedded_identity import verify_shopify_id_token, ShopifyIdTokenError
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..services.shopify_embedded_link import installed_shop_status
from ..services.shopify_embedded_membership import authorize_embedded_identity
from ..services.shopify_managed_installation import (
    ManagedShopifyInstallationError, verify_managed_installation,
    stage_managed_installation,
)

router = APIRouter()

@router.get("/api/shopify/embedded", response_class=HTMLResponse)
def shopify_embedded_home() -> HTMLResponse:
    client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
    # Fail closed if the runtime is not bound to the configured Shopify app.
    if client_id != "c5fc9aed710462d41767477fa9e595c0":
        raise HTTPException(status_code=503, detail="Shopify embedded app is not configured")
    html = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="shopify-api-key" content="c5fc9aed710462d41767477fa9e595c0">
  <title>DIAGLOB — Shopify</title>
  <style>
  *{box-sizing:border-box}body{margin:0;background:#f3f7fc;color:#152e50;font:15px system-ui,sans-serif}
  main{max-width:1440px;margin:auto;padding:28px}
  h1{font-size:28px}p{line-height:1.55}
  .card{background:white;border:1px solid #dce5f0;border-radius:16px;padding:24px;margin:14px 0}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
  .small{font-size:13px;color:#526783}
  button,a.action{display:inline-block;background:#153f75;border:0;border-radius:9px;color:#fff;padding:12px 16px;text-decoration:none;cursor:pointer}
  input{display:block;width:100%;max-width:390px;border:1px solid #bdcddd;border-radius:8px;padding:11px;margin:6px 0 14px}
  label{display:block}h2{margin-top:0}
  [hidden]{display:none!important}
  @media(max-width:600px){main{padding:16px}.card{padding:16px}}
  .tabbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px}.tabbar button{background:#e6edf7;color:#153f75}.tabbar button[aria-current="page"]{background:#153f75;color:white}.searchbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0}.searchbar input{margin:0;max-width:360px}.pager{display:flex;align-items:center;gap:12px;margin-top:16px}.pager button{padding:9px 14px}.pager button:disabled{opacity:.45;cursor:not-allowed}.metricnum{font-size:24px;font-weight:800;margin-top:8px}.metricnum.small{font-size:16px;font-weight:650;overflow-wrap:anywhere;line-height:1.5}.itemrow{padding:12px;border-bottom:1px solid #e0e6ed}.itemrow strong{display:block}.itemrow span{font-size:13px;color:#546980}</style>
  <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
</head>
<body>
  <main>
    <h1>DIAGLOB — Shopify</h1><div class='card' id='welcome'>
    <p id="status" role="status">Validando la sesión de Shopify…</p>
    <section id="shopify-link" hidden aria-label="Vincular usuario Shopify">
      <p>Para autorizar tu usuario de Shopify, entra a Diaglob desde otra pestaña,
      selecciona la tienda conectada y genera un código de vinculación de un solo uso.
      No escribas contraseñas ni tokens de acceso en este formulario.</p>
      <form id="link-form">
        <label>Código de vinculación <input name="code" type="text" autocomplete="off" minlength="40" maxlength="100" required></label>
        <button type="submit">Vincular mi usuario Shopify</button>
      </form>
      <p><a href="https://diaglob.tech/login" target="_blank" rel="noopener noreferrer">Abrir Diaglob para generar código</a></p>
    </section>
    <section id="managed-onboarding" hidden aria-label="Nueva instalación Shopify">
      <p>Shopify confirmó la instalación. Genera un código de 10 minutos para
        asociarla a una tienda de Diaglob desde tu cuenta autorizada.</p>
      <button id="managed-stage" type="button">Generar código de instalación</button>
      <p id="managed-stage-status" role="status"></p>
      <code id="managed-claim-code" style="overflow-wrap:anywhere"></code>
      <p><a href="https://diaglob.tech/shopify/install?managed=1" target="_blank" rel="noopener noreferrer">Continuar en Diaglob</a></p>
    </section>
    </div><section id="overview" class="card" hidden><h2 id="store-title"></h2><p id="store-domain"></p><div class="grid"><div class="card">Conexión: Shopify</div><div class="card">País: <b id="country"></b></div><div class="card">Moneda: <b id="currency"></b></div><div class="card">Acceso: solo lectura</div></div><nav class="tabbar" aria-label="Módulos de Diaglob">
<button type="button" data-panel="home">Resumen</button>
<button type="button" data-panel="products">Productos</button>
<button type="button" data-panel="orders">Pedidos</button>
</nav>
<div id="metrics" class="grid" hidden>
<div class="card"><div class="small">Productos guardados en DIAGLOB</div><div id="metric-products" class="metricnum">—</div></div>
<div class="card"><div class="small">Pedidos registrados</div><div id="metric-orders" class="metricnum">—</div></div>
<div class="card"><div class="small">Última sincronización de productos</div><div id="metric-sync" class="metricnum small">No registrada</div></div>
</div>
<form id="search-form" class="searchbar" hidden><label for="filter-text">Buscar</label><input id="filter-text" name="search" maxlength="100" placeholder="Buscar en esta tienda"><button type="submit">Buscar</button></form>
<div id="section-output" role="status" aria-live="polite"></div>
<div id="pager" class="pager" hidden><button type="button" id="previous-page">Anterior</button><span id="page-status"></span><button type="button" id="next-page">Siguiente</button></div><button type="button" id="logout">Cerrar sesión</button></section><script>
      async function showAuthorizedOverview() {
        const token = await window.shopify.idToken();
        const permission = await fetch('/api/shopify/embedded/authorize', {
          headers: {Authorization: 'Bearer ' + token}, cache: 'no-store'
        });
        if (!permission.ok) return false;
        const result = await permission.json();
        if (!result.authorized) return false;
        const fresh = await window.shopify.idToken();
        const response = await fetch('/api/shopify/embedded/overview', {
          cache: 'no-store', headers: {Authorization: 'Bearer ' + fresh}
        });
        if (!response.ok) return false;
        const data = await response.json();
        document.getElementById('store-title').textContent = data.store_name;
        document.getElementById('store-domain').textContent = data.shop;
        document.getElementById('country').textContent = data.country_code;
        document.getElementById('currency').textContent = data.currency;
        embeddedAccessToken = 'linked-in-memory';
        document.getElementById('welcome').hidden = true;
        document.getElementById('shopify-link').hidden = true;
        document.getElementById('overview').hidden = false;
        await showSection('home');
        return true;
      }
      (async function () {
        const status = document.getElementById('status');
        try {
          if (!window.shopify || typeof window.shopify.idToken !== 'function') {
            throw new Error('Shopify App Bridge no disponible');
          }
          const jwt = await window.shopify.idToken();
          const session = await fetch('/api/shopify/embedded/session', {
            cache: 'no-store', headers: {Authorization: 'Bearer ' + jwt}
          });
          if (!session.ok) throw new Error('Sesión Shopify inválida');
          const info = await session.json();
          if (info.installation_status !== 'connected') {
            // Shopify-managed installation proof never grants access to
            // private DIAGLOB tenants and never stores Shopify credentials.
            const freshToken = await window.shopify.idToken();
            const verification = await fetch('/api/shopify/embedded/managed-install/verify', {
              method: 'POST',
              cache: 'no-store',
              headers: {Authorization: 'Bearer ' + freshToken}
            });
            if (!verification.ok) {
              status.textContent = 'No pudimos confirmar la instalación gestionada de Shopify. Contacta soporte de Diaglob.';
              return;
            }
            status.textContent = 'Shopify confirmó esta instalación. Completa la vinculación con tu cuenta autorizada de Diaglob.';
            document.getElementById('managed-onboarding').hidden = false;
            return;
          }
          if (await showAuthorizedOverview()) return;
          status.textContent = 'Vincula este usuario de Shopify con una cuenta autorizada de Diaglob.';
          document.getElementById('shopify-link').hidden = false;
        } catch (error) {
          status.textContent = 'No pudimos validar tu sesión. Abre Diaglob desde Shopify Admin.';
        }
      })();
      document.getElementById('managed-stage').addEventListener('click', async function () {
        const button = this;
        const status = document.getElementById('managed-stage-status');
        const code = document.getElementById('managed-claim-code');
        button.disabled = true;
        code.textContent = '';
        status.textContent = 'Solicitando autorización temporal…';
        try {
          const token = await window.shopify.idToken();
          const response = await fetch('/api/shopify/embedded/managed-install/stage', {
            method: 'POST', cache: 'no-store',
            headers: {'Authorization': 'Bearer ' + token}
          });
          if (!response.ok) {
            const result = await response.json().catch(() => null);
            const code = result && result.detail && result.detail.code;
            const scopeDiagnostic = result && result.detail;
            const safeCodes = {
              SHOPIFY_APP_CREDENTIALS_REJECTED: 'Shopify rechazó la identidad de la aplicación. Revisa la configuración del backend.',
              SHOPIFY_SESSION_TOKEN_REJECTED: 'Shopify rechazó la sesión actual. Recarga la aplicación desde Shopify Admin.',
              SHOPIFY_TOKEN_GRANT_REJECTED: 'Shopify rechazó el intercambio de credenciales. Revisa la autorización de la aplicación.',
              SHOPIFY_TOKEN_EXCHANGE_REJECTED: 'Shopify rechazó el intercambio de credenciales. Revisa la autorización de la aplicación.',
              SHOPIFY_TOKEN_EXCHANGE_UNAVAILABLE: 'Shopify no pudo procesar el intercambio. Inténtalo más tarde.',
              SHOPIFY_EXPIRING_OFFLINE_TOKEN_REQUIRED: 'Shopify no devolvió un token offline renovable. Se requiere revisar la integración.',
              SHOPIFY_REQUIRED_SCOPES_MISSING: 'La autorización de Shopify no incluye todos los permisos necesarios.',
              SHOPIFY_MANAGED_INSTALL_NOT_CONFIGURED: 'Falta configurar la autorización Shopify en el servidor de DIAGLOB.',
              SHOPIFY_MANAGED_INSTALL_IDENTITY_MISMATCH: 'La tienda autorizada no coincide con la instalación. Contacta soporte.',
              SHOPIFY_MANAGED_INSTALL_GRANT_FAILED: 'DIAGLOB no pudo completar la preparación. Revisa el diagnóstico del servidor.',
            };
            const known = typeof code === 'string' && Object.prototype.hasOwnProperty.call(safeCodes, code);
            let message = known
              ? safeCodes[code]
              : 'No fue posible preparar la instalación. Revisa el código HTTP de la solicitud.';
            if (code === 'SHOPIFY_REQUIRED_SCOPES_MISSING' && scopeDiagnostic) {
              const state = scopeDiagnostic.scope_field_status;
              const allowedScopes = new Set([
                'read_products', 'read_inventory', 'read_orders', 'write_orders',
                'write_draft_orders', 'read_merchant_managed_fulfillment_orders',
                'write_merchant_managed_fulfillment_orders',
              ]);
              const missing = Array.isArray(scopeDiagnostic.missing_scopes)
                ? scopeDiagnostic.missing_scopes.filter(
                  (item) => typeof item === 'string' && allowedScopes.has(item)
                )
                : [];
              if (state === 'absent') {
                message = 'Shopify no informó el campo scope en la respuesta del token offline. Se requiere revisar el intercambio.';
              } else if (state === 'empty_or_invalid') {
                message = 'El campo scope del token offline de Shopify es inválido o está vacío.';
              } else if (missing.length) {
                message += ' Permisos faltantes en el token offline: ' + missing.join(', ') + '.';
              }
            }
            throw new Error(message + (known ? ' (' + code + ')' : ''));
          }
          const grant = await response.json();
          code.textContent = grant.claim_code;
          status.textContent = 'Copia el código y pégalo en la página de instalación de Diaglob. Caduca en 10 minutos.';
          const currentCode = grant.claim_code;
          window.setTimeout(() => {
            if (code.textContent === currentCode) code.textContent = '';
          }, Math.min(600, grant.expires_in_seconds) * 1000);
        } catch (error) {
          status.textContent = error instanceof Error
            ? error.message
            : 'No se pudo completar la preparación de Shopify. Reintenta desde Shopify Admin.';
        } finally {
          button.disabled = false;
        }
      });
      // Product timestamps are stored as naive UTC by the sync worker.
      // Treat such timestamps as UTC, not as the browser's local time.
      // Shopify Admin can be opened from different time zones.
      function formatProductSyncTime(raw) {
        if (typeof raw !== 'string' || !raw.trim()) return 'No registrada';
        const normalized = /(?:Z|[+-]\\d{2}:\\d{2})$/i.test(raw) ? raw : raw + 'Z';
        const date = new Date(normalized);
        if (Number.isNaN(date.getTime())) return 'Fecha no disponible';
        return new Intl.DateTimeFormat('es-CO', {
          dateStyle: 'medium',
          timeStyle: 'short',
          timeZone: 'America/Bogota'
        }).format(date) + ' (Bogotá)';
      }

      let embeddedAccessToken = null;
      let currentSection = 'home';
      let currentPage = 1;
      let totalPages = 1;
      const searchForm = document.getElementById('search-form');
      const pager = document.getElementById('pager');
      const output = document.getElementById('section-output');
      async function showSection(section, keepPage = false) {
        if (!keepPage || section !== currentSection) currentPage = 1;
        currentSection = section;
        searchForm.hidden = !(section === 'products' || section === 'orders');
        pager.hidden = true;
        document.getElementById('metrics').hidden = section !== 'home';
      document.querySelectorAll('[data-panel]').forEach(button => {
          if (button.dataset.panel === section) button.setAttribute('aria-current', 'page');
          else button.removeAttribute('aria-current');
        });
        output.replaceChildren();
        if (section === 'home') {
          output.textContent = 'Datos sincronizados en Diaglob. Las cifras no son consultas en tiempo real a Shopify.';
          if (!embeddedAccessToken) return;
          try {
            const token = await window.shopify.idToken();
            const metrics = await fetch('/api/shopify/embedded/metrics', {
              cache: 'no-store', headers: {
                Authorization: 'Bearer ' + token
              }
            });
            if (!metrics.ok) throw new Error('No se pudieron cargar las métricas.');
            const data = await metrics.json();
            document.getElementById('metric-products').textContent = data.products;
            document.getElementById('metric-orders').textContent = data.orders;
            document.getElementById('metric-sync').textContent = formatProductSyncTime(data.last_product_sync);
          } catch (error) { output.textContent = error.message || 'Error al cargar métricas.'; }
          return;
        }
        if (section === 'conversations' || section === 'automations') {
          output.textContent = 'Este módulo estará disponible próximamente.';
          return;
        }
        if (!embeddedAccessToken) {
          output.textContent = 'Tu sesión ha finalizado. Vuelve a iniciar sesión.';
          return;
        }
        output.textContent = 'Cargando registros de la tienda…';
        try {
          const token = await window.shopify.idToken();
          const response = await fetch('/api/shopify/embedded/data/' + section + '?page=' + currentPage + '&search=' + encodeURIComponent(document.getElementById('filter-text').value.trim()), {
            cache: 'no-store',
            headers: {
              Authorization: 'Bearer ' + token
              }
          });
          if (response.status === 401 || response.status === 403) {
            embeddedAccessToken = null;
            throw new Error('El acceso a la tienda caducó o fue revocado. Vuelve a vincular tu usuario.');
          }
          if (!response.ok) throw new Error('No se pudieron consultar los registros.');
          const result = await response.json();
          output.replaceChildren();
          totalPages = Math.max(1, Math.ceil(result.total / result.limit));
          pager.hidden = false;
          document.getElementById('page-status').textContent = 'Página ' + currentPage + ' de ' + totalPages + ' · ' + result.total + ' registros';
          document.getElementById('previous-page').disabled = currentPage <= 1;
          document.getElementById('next-page').disabled = currentPage >= totalPages;
          if (!result.items.length) {
            output.textContent = 'No hay ' + (section === 'products' ? 'productos' : 'pedidos') + ' sincronizados en esta tienda.';
            return;
          }
          result.items.forEach(item => {
            const line = document.createElement('div');
            line.className = 'itemrow';
            const title = document.createElement('strong');
            title.textContent = section === 'products' ? item.title : item.order_number;
            const details = document.createElement('span');
            details.textContent = section === 'products'
              ? [item.vendor || 'Sin proveedor', item.active ? 'Activo' : 'Inactivo'].join(' · ')
              : [item.total_amount + ' ' + item.currency, item.financial_status || 'Sin estado de pago', item.fulfillment_status || 'Pendiente'].join(' · ');
            line.append(title, details);
            output.appendChild(line);
          });
        } catch (error) {
          output.textContent = error.message || 'No se pudieron cargar los datos.';
        }
      }
        searchForm.addEventListener('submit', event => {
        event.preventDefault();
        currentPage = 1;
        showSection(currentSection, true);
      });
      document.getElementById('previous-page').addEventListener('click', () => {
        if (currentPage > 1) { currentPage--; showSection(currentSection, true); }
      });
      document.getElementById('next-page').addEventListener('click', () => {
        if (currentPage < totalPages) { currentPage++; showSection(currentSection, true); }
      });
      document.querySelectorAll('[data-panel]').forEach(button =>
        button.addEventListener('click', () => showSection(button.dataset.panel))
      );
      document.getElementById('logout').addEventListener('click', () => {
        embeddedAccessToken = null;
        output.replaceChildren();
        document.getElementById('overview').hidden = true;
        document.getElementById('welcome').hidden = false;
        document.getElementById('shopify-link').hidden = false;
      });
      document.getElementById('link-form').addEventListener('submit', async function (event) {
        event.preventDefault();
        const form = event.currentTarget;
        const status = document.getElementById('status');
        const submit = form.querySelector('button');
        const field = form.elements.namedItem('code');
        submit.disabled = true;
        try {
          const token = await window.shopify.idToken();
          const response = await fetch('/api/shopify/embedded/link', {
            method: 'POST', cache: 'no-store',
            headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            body: JSON.stringify({code: field.value.trim()})
          });
          if (!response.ok) throw new Error('El código es inválido, expiró o no corresponde a esta tienda.');
          field.value = '';
          if (!await showAuthorizedOverview()) throw new Error('No pudimos verificar la vinculación.');
        } catch (error) {
          status.textContent = error.message || 'No fue posible completar la vinculación.';
        } finally {
          field.value = '';
          submit.disabled = false;
        }
      });
    </script>
  </main>
</body>
</html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})

# An ID token proves Shopify identity only; it is NOT a Diaglob tenant grant.
_embedded_bearer = HTTPBearer(auto_error=False)


@router.get("/api/shopify/embedded/session")
def verify_embedded_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    db: Session = Depends(get_db),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        verified = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    return {
        "authenticated": True,
        "shop": verified["shop"],
        "installation_status": installed_shop_status(db, verified["shop"]),
        "tenant_authorized": False
              }

@router.post("/api/shopify/embedded/managed-install/verify")
def embedded_managed_installation_verify(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
) -> dict:
    """No token storage, tenant bootstrap, billing or automatic account linking."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid Shopify session") from exc
    try:
        return verify_managed_installation(
            identity=identity, id_token=credentials.credentials,
        )
    except ManagedShopifyInstallationError as exc:
        raise HTTPException(
            status_code=502, detail="Shopify managed installation not verified",
        ) from exc


@router.post("/api/shopify/embedded/managed-install/stage")
def embedded_managed_installation_stage(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    db: Session = Depends(get_db),
) -> dict:
    """Explicit Shopify staff action to stage an encrypted, expiring grant.

    The response is a 10-minute one-use claim code, not an access token.
    A separately authenticated DIAGLOB store owner must complete the claim.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid Shopify session") from exc
    try:
        return stage_managed_installation(db, identity=identity, id_token=credentials.credentials)
    except ManagedShopifyInstallationError as exc:
        # Only return recognized internal reason codes. Never leak the OAuth
        # response body, subject token or provider error_description.
        public_codes = {
            "INVALID_SHOPIFY_SHOP",
            "INVALID_SHOPIFY_SESSION",
            "SHOPIFY_MANAGED_INSTALL_NOT_CONFIGURED",
            "SHOPIFY_APP_CREDENTIALS_REJECTED",
            "SHOPIFY_SESSION_TOKEN_REJECTED",
            "SHOPIFY_TOKEN_GRANT_REJECTED",
            "SHOPIFY_TOKEN_EXCHANGE_REJECTED",
            "SHOPIFY_TOKEN_EXCHANGE_UNAVAILABLE",
            "SHOPIFY_EXPIRING_OFFLINE_TOKEN_REQUIRED",
            "SHOPIFY_REQUIRED_SCOPES_MISSING",
            "SHOPIFY_MANAGED_INSTALL_IDENTITY_MISMATCH",
            "INVALID_SHOPIFY_MANAGED_GRANT",
            "SHOPIFY_MANAGED_INSTALL_GRANT_FAILED",
        }
        code = str(exc) if str(exc) in public_codes else "SHOPIFY_MANAGED_INSTALL_GRANT_FAILED"
        status_code = 503 if code == "SHOPIFY_MANAGED_INSTALL_NOT_CONFIGURED" else 502
        detail = {"code": code, "message": "No fue posible preparar la autorización Shopify."}
        if code == "SHOPIFY_REQUIRED_SCOPES_MISSING":
            # Only expose names from the PUBLIC set of app-required scopes.
            # The OAuth token, grant response, and other provider fields
            # never cross this boundary.
            from ..shopify_oauth import SHOPIFY_SCOPES
            permitted_names = set(SHOPIFY_SCOPES.split(","))
            missing = getattr(exc, "missing_scopes", ())
            if isinstance(missing, tuple):
                detail["missing_scopes"] = sorted(
                    {s for s in missing if isinstance(s, str) and s in permitted_names}
                )
            status = getattr(exc, "scope_field_status", None)
            if status in {"present", "absent", "empty_or_invalid"}:
                detail["scope_field_status"] = status
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc


@router.get("/api/shopify/embedded/authorize")
def authorize_embedded_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    db: Session = Depends(get_db),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    return authorize_embedded_identity(db, identity)


@router.get("/api/shopify/embedded/overview")
def embedded_overview(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    db: Session = Depends(get_db),
) -> dict:
    """Read-only store metadata; fresh dual-token authorization on every request."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    granted = authorize_embedded_identity(db, identity)
    from ..models import Store
    store = db.query(Store).filter(
        Store.id == granted["store_id"],
        Store.organization_id == granted["organization_id"],
        Store.active.is_(True),
        Store.deleted.is_(False),
    ).first()
    if store is None:
        raise HTTPException(status_code=403, detail="Store unavailable")
    return {
        "shop": identity["shop"],
        "store_name": store.name,
        "country_code": store.country_code,
        "currency": store.currency,
        "status": "connected",
        "mode": "read_only"
              }

@router.get("/api/shopify/embedded/data/{section}")
def embedded_store_data(
    section: str,
    page: int = 1,
    search: str = "",
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    db: Session = Depends(get_db),
) -> dict:
    """Bounded, redacted, store-scoped reads; no customer PII or mutations."""
    if not 1 <= page <= 10000 or len(search) > 100:
        raise HTTPException(status_code=422, detail="Invalid pagination or search")
    if section not in ("products", "orders"):
        raise HTTPException(status_code=404, detail="Unknown section")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    authorized = authorize_embedded_identity(db, identity)
    from ..models import Product, Order
    model = Product if section == "products" else Order
    field = Product.title if section == "products" else Order.order_number
    scoped = db.query(model).filter(
        model.organization_id == authorized["organization_id"],
        model.store_id == authorized["store_id"],
    )
    if search.strip():
        scoped = scoped.filter(field.ilike("%" + search.strip().replace("%", r"\%").replace("_", r"\_") + "%", escape="\\"))
    total = scoped.count()
    page_size = 20
    if section == "products":
        rows = scoped.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"section": section, "items": [
            {"id": row.id, "title": row.title, "vendor": row.vendor,
             "active": row.active, "shopify_product_id": row.shopify_product_id}
            for row in rows
        ], "limit": page_size, "page": page, "total": total}
    rows = scoped.order_by(Order.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"section": section, "items": [
        {"id": row.id, "order_number": row.order_number,
         "total_amount": str(row.total_amount), "currency": row.currency,
         "financial_status": row.financial_status,
         "fulfillment_status": row.fulfillment_status}
        for row in rows
    ], "limit": page_size, "page": page, "total": total}

@router.get("/api/shopify/embedded/metrics")
def embedded_metrics(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    db: Session = Depends(get_db),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        verified = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    grant = authorize_embedded_identity(db, verified)
    from ..models import Product, Order, CommerceConnection
    scope = {"organization_id": grant["organization_id"], "store_id": grant["store_id"]}
    product_count = db.query(Product).filter_by(**scope).count()
    order_count = db.query(Order).filter_by(**scope).count()
    connection = db.query(CommerceConnection).filter_by(
        **scope, provider="shopify", status="connected"
    ).first()
    return {
        "products": product_count,
        "orders": order_count,
        "last_product_sync": connection.last_sync_at.isoformat() if connection and connection.last_sync_at else None,
        "mode": "read_only"
              }
