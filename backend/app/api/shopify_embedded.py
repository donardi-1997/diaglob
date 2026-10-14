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
  <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
</head>
<body>
  <main>
    <h1>DIAGLOB</h1>
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
    <script>
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
          status.textContent = 'Cuenta Diaglob autorizada para esta tienda. Ya puedes acceder al panel Diaglob.';
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
