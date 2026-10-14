"""Dedicated public entrypoint for Shopify embedded App Home.

No tenant data, Shopify Admin API token or Cognito session is exposed here.
Shopify ID-token validation is implemented separately before protected features.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..services.shopify_embedded_identity import verify_shopify_id_token, ShopifyIdTokenError
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..services.shopify_embedded_link import installed_shop_status
from ..services.shopify_embedded_authorization import authorize_embedded_store
from ..auth import AWS_REGION, COGNITO_CLIENT_ID

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
  .tabbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px}.tabbar button{background:#e6edf7;color:#153f75}.tabbar button[aria-current="page"]{background:#153f75;color:white}.searchbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0}.searchbar input{margin:0;max-width:360px}.pager{display:flex;align-items:center;gap:12px;margin-top:16px}.pager button{padding:9px 14px}.pager button:disabled{opacity:.45;cursor:not-allowed}.metricnum{font-size:24px;font-weight:800;margin-top:8px}.itemrow{padding:12px;border-bottom:1px solid #e0e6ed}.itemrow strong{display:block}.itemrow span{font-size:13px;color:#546980}</style>
  <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
</head>
<body>
  <main>
    <h1>DIAGLOB — Shopify</h1><div class='card' id='welcome'>
    <p id="status" role="status">Validando la sesión de Shopify…</p>
    <section id="diaglob-login" hidden aria-label="Ingreso a Diaglob">
      <p>Inicia sesión con tu cuenta de Diaglob para confirmar tus permisos sobre esta tienda.</p>
      <form id="login-form">
        <label>Correo <input name="email" type="email" autocomplete="username" required></label>
        <label>Contraseña <input name="password" type="password" autocomplete="current-password" required></label>
        <button type="submit">Validar acceso</button>
      </form>
    </section>
    <p><a id="portal-link" hidden href="https://diaglob.tech/login" target="_blank" rel="noopener noreferrer">Abrir panel Diaglob</a></p>
    </div><section id="overview" class="card" hidden><h2 id="store-title"></h2><p id="store-domain"></p><div class="grid"><div class="card">Conexión: Shopify</div><div class="card">País: <b id="country"></b></div><div class="card">Moneda: <b id="currency"></b></div><div class="card">Acceso: solo lectura</div></div><nav class="tabbar" aria-label="Módulos de Diaglob">
<button type="button" data-panel="home">Resumen</button>
<button type="button" data-panel="products">Productos</button>
<button type="button" data-panel="orders">Pedidos</button>
<button type="button" data-panel="conversations">Conversaciones</button>
<button type="button" data-panel="automations">Automatizaciones</button>
</nav>
<div id="metrics" class="grid" hidden>
<div class="card"><div class="small">Productos sincronizados</div><div id="metric-products" class="metricnum">—</div></div>
<div class="card"><div class="small">Pedidos registrados</div><div id="metric-orders" class="metricnum">—</div></div>
<div class="card"><div class="small">Última sincronización de productos</div><div id="metric-sync" class="metricnum small">No registrada</div></div>
</div>
<form id="search-form" class="searchbar" hidden><label for="filter-text">Buscar</label><input id="filter-text" name="search" maxlength="100" placeholder="Buscar en esta tienda"><button type="submit">Buscar</button></form>
<div id="section-output" role="status" aria-live="polite"></div>
<div id="pager" class="pager" hidden><button type="button" id="previous-page">Anterior</button><span id="page-status"></span><button type="button" id="next-page">Siguiente</button></div><button type="button" id="logout">Cerrar sesión</button></section><script>
      (async function () {
        const status = document.getElementById('status');
        try {
          if (!window.shopify || typeof window.shopify.idToken !== 'function') {
            throw new Error('Shopify App Bridge no disponible');
          }
          const token = await window.shopify.idToken();
          const response = await fetch('/api/shopify/embedded/session', {
            headers: { Authorization: 'Bearer ' + token },
            cache: 'no-store'
          });
          if (!response.ok) throw new Error('Sesión no válida');
          const identity = await response.json();
          if (identity.installation_status === 'connected') {
            status.textContent = 'Shopify verificado y tienda conectada a Diaglob. Para acceder al panel, inicia sesión con tu cuenta Diaglob.';
          } else {
            status.textContent = 'Shopify verificado. Falta vincular esta tienda desde tu cuenta de Diaglob.';
          }
          const link = document.getElementById('portal-link');
          if (link) link.hidden = false;
          if (identity.installation_status === 'connected') {
            document.getElementById('diaglob-login').hidden = false;
          }
        } catch (error) {
          status.textContent = 'No pudimos validar tu sesión. Abre Diaglob desde Shopify Admin.';
        }
      })();
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
                Authorization: 'Bearer ' + token,
                'X-Diaglob-Authorization': 'Bearer ' + embeddedAccessToken
              }
            });
            if (!metrics.ok) throw new Error('No se pudieron cargar las métricas.');
            const data = await metrics.json();
            document.getElementById('metric-products').textContent = data.products;
            document.getElementById('metric-orders').textContent = data.orders;
            document.getElementById('metric-sync').textContent = data.last_product_sync || 'No registrada';
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
              Authorization: 'Bearer ' + token,
              'X-Diaglob-Authorization': 'Bearer ' + embeddedAccessToken
            }
          });
          if (response.status === 401 || response.status === 403) {
            embeddedAccessToken = null;
            throw new Error('Tu sesión expiró o ya no tienes permisos. Vuelve a iniciar sesión.');
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
      document.querySelectorAll('[data-panel]').forEach(button =>
        button.addEventListener('click', () => showSection(button.dataset.panel))
      );
      document.getElementById('logout').addEventListener('click', () => {
        embeddedAccessToken = null;
        output.replaceChildren();
        document.getElementById('overview').hidden = true;
        document.getElementById('welcome').hidden = false;
        document.getElementById('diaglob-login').hidden = false;
      });
      document.getElementById('login-form').addEventListener('submit', async function (event) {
        event.preventDefault();
        const form = event.currentTarget;
        const status = document.getElementById('status');
        const submit = form.querySelector('button');
        submit.disabled = true;
        const email = form.elements.namedItem('email').value;
        const passwordInput = form.elements.namedItem('password');
        const password = passwordInput.value;
        try {
          const cognito = await fetch('https://cognito-idp.__AWS_REGION__.amazonaws.com/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-amz-json-1.1',
              'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth'
            },
            body: JSON.stringify({
              AuthFlow: 'USER_PASSWORD_AUTH',
              ClientId: '__COGNITO_CLIENT_ID__',
              AuthParameters: { USERNAME: email, PASSWORD: password }
            })
          });
          const login = await cognito.json();
          if (!cognito.ok || !login.AuthenticationResult?.AccessToken) {
            throw new Error('No fue posible iniciar sesión. Usa el portal Diaglob si tu cuenta requiere pasos adicionales.');
          }
          const shopifyToken = await window.shopify.idToken();
          const authorization = await fetch('/api/shopify/embedded/authorize', {
            headers: {
              Authorization: 'Bearer ' + shopifyToken,
              'X-Diaglob-Authorization': 'Bearer ' + login.AuthenticationResult.AccessToken
            },
            cache: 'no-store'
          });
          if (!authorization.ok) throw new Error('Tu cuenta Diaglob no tiene acceso autorizado a esta tienda.');
          const result = await authorization.json();
          if (!result.authorized) throw new Error('No se pudo comprobar el acceso.');
          const overviewToken = await window.shopify.idToken();
          const summary = await fetch('/api/shopify/embedded/overview', {
            cache: 'no-store',
            headers: {
              Authorization: 'Bearer ' + overviewToken,
              'X-Diaglob-Authorization': 'Bearer ' + login.AuthenticationResult.AccessToken
            }
          });
          if (!summary.ok) throw new Error('No se pudo cargar el resumen.');
          const data = await summary.json();
          document.getElementById('store-title').textContent = data.store_name;
          document.getElementById('store-domain').textContent = data.shop;
          document.getElementById('country').textContent = data.country_code;
          document.getElementById('currency').textContent = data.currency;
          document.getElementById('welcome').hidden = true;
          embeddedAccessToken = login.AuthenticationResult.AccessToken;
          document.getElementById('overview').hidden = false;
          await showSection('home');
          document.getElementById('diaglob-login').hidden = true;
        } catch (error) {
          status.textContent = error.message || 'No fue posible comprobar la autorización.';
        } finally {
          passwordInput.value = '';
          submit.disabled = false;
        }
      });
    </script>
  </main>
</body>
</html>"""
    html = html.replace("__AWS_REGION__", AWS_REGION).replace("__COGNITO_CLIENT_ID__", COGNITO_CLIENT_ID)
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
        "tenant_authorized": False,
    }

@router.get("/api/shopify/embedded/authorize")
def authorize_embedded_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    diaglob_authorization: str | None = Header(None, alias="X-Diaglob-Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    if not diaglob_authorization or not diaglob_authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Diaglob Cognito access token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    return authorize_embedded_store(
        db, identity["shop"], diaglob_authorization[len("Bearer "):]
    )

@router.get("/api/shopify/embedded/overview")
def embedded_overview(
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    diaglob_authorization: str | None = Header(None, alias="X-Diaglob-Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    """Read-only store metadata; fresh dual-token authorization on every request."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    if not diaglob_authorization or not diaglob_authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Diaglob access token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    granted = authorize_embedded_store(
        db, identity["shop"], diaglob_authorization[len("Bearer "):]
    )
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
        "mode": "read_only",
    }

@router.get("/api/shopify/embedded/data/{section}")
def embedded_store_data(
    section: str,
    page: int = 1,
    search: str = "",
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    diaglob_authorization: str | None = Header(None, alias="X-Diaglob-Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    """Bounded, redacted, store-scoped reads; no customer PII or mutations."""
    if not 1 <= page <= 10000 or len(search) > 100:
        raise HTTPException(status_code=422, detail="Invalid pagination or search")
    if section not in ("products", "orders"):
        raise HTTPException(status_code=404, detail="Unknown section")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    if not diaglob_authorization or not diaglob_authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Diaglob access token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    authorized = authorize_embedded_store(
        db, identity["shop"], diaglob_authorization[len("Bearer "):]
    )
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
    diaglob_authorization: str | None = Header(None, alias="X-Diaglob-Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    if not diaglob_authorization or not diaglob_authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Diaglob access token required")
    try:
        verified = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Shopify session")
    grant = authorize_embedded_store(db, verified["shop"], diaglob_authorization[7:])
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
        "mode": "read_only",
    }
