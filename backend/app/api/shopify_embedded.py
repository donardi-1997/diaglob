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
    <p><a id="portal-link" hidden href="https://diaglob.tech/login">Abrir Diaglob e iniciar sesión</a></p>
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
        } catch (error) {
          status.textContent = 'No pudimos validar tu sesión. Abre Diaglob desde Shopify Admin.';
        }
      })();
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
        "tenant_authorized": False,
    }
