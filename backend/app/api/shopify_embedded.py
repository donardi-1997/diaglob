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
  main{max-width:1120px;margin:auto;padding:32px}
  h1{font-size:28px}p{line-height:1.55}
  .card{background:white;border:1px solid #dce5f0;border-radius:16px;padding:24px;margin:14px 0}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
  .small{font-size:13px;color:#526783}
  button,a.action{display:inline-block;background:#153f75;border:0;border-radius:9px;color:#fff;padding:12px 16px;text-decoration:none;cursor:pointer}
  input{display:block;width:100%;max-width:390px;border:1px solid #bdcddd;border-radius:8px;padding:11px;margin:6px 0 14px}
  label{display:block}h2{margin-top:0}
  [hidden]{display:none!important}
  @media(max-width:600px){main{padding:16px}.card{padding:16px}}
  .tabbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px}.tabbar button{background:#e6edf7;color:#153f75}.tabbar button[aria-current="page"]{background:#153f75;color:white}.itemrow{padding:12px;border-bottom:1px solid #e0e6ed}.itemrow strong{display:block}.itemrow span{font-size:13px;color:#546980}</style>
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
<div id="section-output" role="status" aria-live="polite"></div><button type="button" id="logout">Cerrar sesión</button></section><script>
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
      document.getElementById('logout').addEventListener('click', () => {
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
          document.getElementById('overview').hidden = false;
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
    credentials: HTTPAuthorizationCredentials | None = Depends(_embedded_bearer),
    diaglob_authorization: str | None = Header(None, alias="X-Diaglob-Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    """Bounded, redacted, store-scoped reads; no customer PII or mutations."""
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
    if section == "products":
        rows = db.query(Product).filter(
            Product.organization_id == authorized["organization_id"],
            Product.store_id == authorized["store_id"],
        ).order_by(Product.id.desc()).limit(50).all()
        return {"section": section, "items": [
            {"id": row.id, "title": row.title, "vendor": row.vendor,
             "active": row.active, "shopify_product_id": row.shopify_product_id}
            for row in rows
        ], "limit": 50}
    rows = db.query(Order).filter(
        Order.organization_id == authorized["organization_id"],
        Order.store_id == authorized["store_id"],
    ).order_by(Order.id.desc()).limit(50).all()
    return {"section": section, "items": [
        {"id": row.id, "order_number": row.order_number,
         "total_amount": str(row.total_amount), "currency": row.currency,
         "financial_status": row.financial_status,
         "fulfillment_status": row.fulfillment_status}
        for row in rows
    ], "limit": 50}
