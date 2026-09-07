"""Google OAuth / Drive / Sheets HTTP layer.

Extracted from main.py (Block 4).  Pure Google-connectivity endpoints only;
knowledge-base provisioning endpoints that happen to call Google remain in
main.py and will move in Block 5.
"""

import json
import logging
import os
import secrets
from datetime import datetime, timedelta

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bedrock_ingestion import map_google_api_error
from ..db import get_db
from ..google_security import (
    decrypt_google_secret,
    encrypt_google_secret,
)
from ..models import (
    GoogleConnection,
    GoogleOAuthState,
    OrganizationMembership,
)
from .deps import require_permission

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class GoogleOAuthStartResponse(BaseModel):
    authorization_url: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_google_client_id() -> str:
    val = os.getenv("GOOGLE_CLIENT_ID", "")
    if not val:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is not configured"
        )
    return val


def _get_google_client_secret() -> str:
    val = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not val:
        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is not configured"
        )
    return val


def _get_google_redirect_uri() -> str:
    return os.getenv(
        "GOOGLE_REDIRECT_URI",
        "https://api.diaglob.tech"
        "/api/integrations/google/oauth/callback",
    )


def _google_connect_frontend_url(
    status: str,
) -> str:
    base_url = os.getenv(
        "FRONTEND_URL",
        "https://diaglob.tech",
    ).strip().rstrip("/")
    return f"{base_url}?google={status}"


def _connection_has_drive_scope(
    connection: GoogleConnection,
) -> bool:
    """Check if connection has drive.readonly scope."""
    if not connection.scopes:
        return False
    return "drive.readonly" in connection.scopes


def _require_drive_scope(
    connection: GoogleConnection,
) -> None:
    """Raise 403 if connection lacks drive scope."""
    if not _connection_has_drive_scope(connection):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_SCOPES",
                "message": (
                    "Additional Google permissions "
                    "required for Drive access."
                ),
                "required_scope": "drive.readonly",
            },
        )


def _refresh_google_token(
    connection: GoogleConnection,
    db: Session,
) -> bool:
    """Attempt to refresh an expired Google token.

    Returns True if refresh succeeded.
    Updates connection in-place.
    """
    if not connection.refresh_token_encrypted:
        return False

    try:
        refresh_token = decrypt_google_secret(
            connection.refresh_token_encrypted
        )
        client_id = _get_google_client_id()
        client_secret = _get_google_client_secret()

        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        new_access = data.get("access_token", "")
        expires_in = data.get("expires_in", 3600)
        new_refresh = data.get("refresh_token")

        if not new_access:
            return False

        connection.access_token_encrypted = (
            encrypt_google_secret(new_access)
        )
        connection.token_expiry = (
            datetime.utcnow()
            + timedelta(seconds=expires_in)
        )
        # Only overwrite if Google returned a new
        # refresh token
        if new_refresh:
            connection.refresh_token_encrypted = (
                encrypt_google_secret(new_refresh)
            )
        connection.status = "connected"
        connection.updated_at = datetime.utcnow()
        db.commit()
        return True

    except Exception:
        connection.status = "token_expired"
        connection.updated_at = datetime.utcnow()
        db.commit()
        return False


def _get_valid_google_token(
    connection: GoogleConnection,
    db: Session,
) -> str | None:
    """Get a valid access token, refreshing if needed.

    Returns decrypted access token or None.
    """
    if not connection.access_token_encrypted:
        return None

    # Check if token is still valid (with 5min buffer)
    if (
        connection.token_expiry
        and connection.token_expiry
        > datetime.utcnow()
        + timedelta(minutes=5)
    ):
        return decrypt_google_secret(
            connection.access_token_encrypted
        )

    # Try refresh
    refreshed = _refresh_google_token(
        connection, db
    )
    if refreshed:
        return decrypt_google_secret(
            connection.access_token_encrypted
        )

    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/integrations/google/status")
def get_google_status(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            != "revoked",
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "email": None,
            "status": None,
        }

    return {
        "connected": connection.status == "connected",
        "email": connection.email,
        "status": connection.status,
        "connected_at": (
            connection.connected_at.isoformat()
            if connection.connected_at
            else None
        ),
    }


@router.get(
    "/api/integrations/google/oauth/start"
)
def start_google_oauth(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        client_id = _get_google_client_id()
        redirect_uri = _get_google_redirect_uri()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "GOOGLE_NOT_CONFIGURED",
                "message": str(exc),
            },
        ) from exc

    # Clean up old unused states for this org
    (
        db.query(GoogleOAuthState)
        .filter(
            GoogleOAuthState.organization_id
            == membership.organization_id,
            GoogleOAuthState.used.is_(False),
        )
        .update({"used": True})
    )

    state_token = secrets.token_urlsafe(32)
    scopes_str = " ".join(GOOGLE_SCOPES)

    oauth_state = GoogleOAuthState(
        state_token=state_token,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        scopes=scopes_str,
        expires_at=datetime.utcnow()
        + timedelta(minutes=10),
        used=False,
    )
    db.add(oauth_state)
    db.commit()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes_str,
        "state": state_token,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }

    query_string = "&".join(
        f"{k}={v}" for k, v in params.items()
    )
    auth_url = (
        f"{GOOGLE_AUTH_URL}?{query_string}"
    )

    return {
        "authorization_url": auth_url,
    }


@router.get(
    "/api/integrations/google/oauth/callback"
)
def google_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    params = dict(request.query_params)

    code = params.get("code", "")
    state_token = params.get("state", "")
    error = params.get("error", "")

    if error:
        frontend_url = (
            _google_connect_frontend_url("error")
        )
        return RedirectResponse(
            url=frontend_url, status_code=302
        )

    if not code or not state_token:
        raise HTTPException(
            status_code=400,
            detail="Missing code or state",
        )

    oauth_state = (
        db.query(GoogleOAuthState)
        .filter(
            GoogleOAuthState.state_token
            == state_token,
            GoogleOAuthState.used.is_(False),
        )
        .first()
    )

    if not oauth_state:
        raise HTTPException(
            status_code=400,
            detail="Invalid or used OAuth state",
        )

    if (
        oauth_state.expires_at
        < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail="OAuth state expired",
        )

    # Consume the state before the external exchange so a failed exchange
    # cannot make the state reusable through a transaction rollback.
    oauth_state.used = True
    db.commit()

    # Exchange code for tokens
    try:
        client_id = _get_google_client_id()
        client_secret = _get_google_client_secret()
        redirect_uri = _get_google_redirect_uri()

        token_response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        token_response.raise_for_status()
        token_data = token_response.json()

    except Exception as exc:
        frontend_url = (
            _google_connect_frontend_url("error")
        )
        return RedirectResponse(
            url=frontend_url, status_code=302
        )

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)
    granted_scopes = token_data.get("scope", "")

    if not access_token:
        frontend_url = (
            _google_connect_frontend_url("error")
        )
        return RedirectResponse(
            url=frontend_url, status_code=302
        )

    # Get user email (best effort, not critical)
    user_email = None
    try:
        user_info_resp = httpx.get(
            "https://www.googleapis.com/"
            "oauth2/v3/userinfo",
            headers={
                "Authorization": (
                    f"Bearer {access_token}"
                ),
            },
            timeout=10,
        )
        if user_info_resp.status_code == 200:
            user_info = user_info_resp.json()
            user_email = user_info.get("email")
    except Exception:
        pass

    # Encrypt tokens
    encrypted_access = encrypt_google_secret(
        access_token
    )
    encrypted_refresh = (
        encrypt_google_secret(refresh_token)
        if refresh_token
        else None
    )

    # Upsert GoogleConnection
    existing = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == oauth_state.organization_id,
        )
        .first()
    )

    token_expiry = (
        datetime.utcnow()
        + timedelta(seconds=expires_in)
    )

    if existing:
        existing.access_token_encrypted = (
            encrypted_access
        )
        # Only overwrite refresh token if Google
        # returned a new one
        if refresh_token:
            existing.refresh_token_encrypted = (
                encrypted_refresh
            )
        existing.token_expiry = token_expiry
        existing.scopes = " ".join(sorted(
            set((existing.scopes or "").split())
            | set(granted_scopes.split())
        ))
        existing.email = (
            user_email or existing.email
        )
        existing.status = "connected"
        existing.connected_at = datetime.utcnow()
        existing.revoked_at = None
        existing.updated_at = datetime.utcnow()
    else:
        connection = GoogleConnection(
            organization_id=(
                oauth_state.organization_id
            ),
            user_id=oauth_state.user_id,
            email=user_email,
            access_token_encrypted=encrypted_access,
            refresh_token_encrypted=encrypted_refresh,
            token_expiry=token_expiry,
            scopes=granted_scopes,
            status="connected",
            connected_at=datetime.utcnow(),
        )
        db.add(connection)

    db.commit()

    frontend_url = (
        _google_connect_frontend_url("connected")
    )
    return RedirectResponse(
        url=frontend_url, status_code=302
    )


@router.delete("/api/integrations/google")
def disconnect_google(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            != "revoked",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="No Google connection found",
        )

    # Try to revoke at Google (best effort)
    try:
        access_token = decrypt_google_secret(
            connection.access_token_encrypted
        )
        httpx.post(
            GOOGLE_REVOKE_URL,
            params={"token": access_token},
            timeout=10,
        )
    except Exception:
        pass

    connection.status = "revoked"
    connection.revoked_at = datetime.utcnow()
    connection.updated_at = datetime.utcnow()
    db.commit()

    return {"ok": True, "status": "revoked"}


# --- Google: List Sheets ---


@router.get("/api/integrations/google/sheets")
async def list_google_sheets(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        async with httpx.AsyncClient(
            timeout=30
        ) as client:
            resp = await client.get(
                "https://www.googleapis.com/"
                "drive/v3/files",
                headers={
                    "Authorization": (
                        f"Bearer {access_token}"
                    ),
                },
                params={
                    "q": (
                        "mimeType="
                        "'application/"
                        "vnd.google-apps.spreadsheet'"
                    ),
                    "fields": (
                        "files(id,name,"
                        "modifiedTime)"
                    ),
                    "pageSize": "100",
                    "orderBy": "modifiedTime desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        sheets = [
            {
                "spreadsheet_id": f["id"],
                "name": f.get("name", "Untitled"),
                "modified_time": f.get(
                    "modifiedTime"
                ),
            }
            for f in data.get("files", [])
        ]

        return {"sheets": sheets}

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc


# --- Google: List Tabs ---


@router.get(
    "/api/integrations/google/sheets/"
    "{spreadsheet_id}/tabs"
)
async def list_google_sheet_tabs(
    spreadsheet_id: str,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        from ..google_sheets_client import (
            get_spreadsheet_metadata,
        )

        metadata = await get_spreadsheet_metadata(
            access_token, spreadsheet_id
        )
        return {
            "title": metadata["title"],
            "tabs": metadata["sheets"],
        }

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc


# --- Scope check endpoint ---


@router.get(
    "/api/integrations/google/drive/scopes"
)
def check_google_drive_scopes(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            != "revoked",
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "has_drive_scope": False,
            "scopes": [],
        }

    has_drive = _connection_has_drive_scope(
        connection
    )

    return {
        "connected": True,
        "has_drive_scope": has_drive,
        "scopes": (
            connection.scopes.split()
            if connection.scopes
            else []
        ),
    }


# --- Expand scopes (re-authorize with drive.readonly) ---


@router.get(
    "/api/integrations/google/oauth/expand-scopes"
)
def expand_google_scopes(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    client_id = _get_google_client_id()
    redirect_uri = _get_google_redirect_uri()

    # Clean old states for this org
    (
        db.query(GoogleOAuthState)
        .filter(
            GoogleOAuthState.organization_id
            == membership.organization_id,
            GoogleOAuthState.used.is_(False),
        )
        .update({"used": True})
    )
    db.flush()

    state_token = secrets.token_urlsafe(32)
    scopes_str = " ".join(GOOGLE_DRIVE_SCOPES)

    oauth_state = GoogleOAuthState(
        state_token=state_token,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        scopes=scopes_str,
        expires_at=datetime.utcnow()
        + timedelta(minutes=10),
        used=False,
    )
    db.add(oauth_state)
    db.commit()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes_str,
        "state": state_token,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }

    query_string = "&".join(
        f"{k}={v}" for k, v in params.items()
    )
    auth_url = (
        f"{GOOGLE_AUTH_URL}?{query_string}"
    )

    return {
        "authorization_url": auth_url,
    }


# --- Drive: list files (file picker) ---


@router.get(
    "/api/integrations/google/drive/files"
)
async def list_drive_files_endpoint(
    query: str = "",
    page_token: str | None = None,
    mime_type: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        from ..google_drive_client import (
            list_drive_files,
        )

        result = await list_drive_files(
            access_token,
            search=query,
            page_token=page_token,
            mime_types={mime_type} if mime_type else None,
        )

        files = []
        for f in result.get("files", []):
            files.append({
                "id": f["id"],
                "name": f.get("name", "Untitled"),
                "mime_type": f.get("mimeType", ""),
                "modified_time": f.get(
                    "modifiedTime"
                ),
                "size": f.get("size"),
                "parents": f.get("parents", []),
            })

        return {
            "files": files,
            "next_page_token": result.get(
                "nextPageToken"
            ),
        }

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc


# --- Drive: list folders (folder picker) ---


@router.get(
    "/api/integrations/google/drive/folders"
)
async def list_drive_folders_endpoint(
    query: str = "",
    page_token: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        from ..google_drive_client import (
            list_drive_folders,
        )

        result = await list_drive_folders(
            access_token,
            search=query,
            page_token=page_token,
        )

        folders = []
        for f in result.get("folders", []):
            folders.append({
                "id": f["id"],
                "name": f.get("name", "Untitled"),
                "modified_time": f.get(
                    "modifiedTime"
                ),
            })

        return {
            "folders": folders,
            "next_page_token": result.get(
                "nextPageToken"
            ),
        }

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
