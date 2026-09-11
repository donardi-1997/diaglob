"""
Tests for Google Sheets Knowledge Base integration.

Covers:
- google_security.py: encrypt/decrypt
- google_sheets_client.py: URL parsing, CSV normalization, limits
- bedrock_ingestion.py: start/status/error mapping
- API endpoints: OAuth, status, sheets, tabs, add source, sync, ingestion status
- Tenant isolation, duplicate prevention, idempotent sync
"""

import asyncio
import csv
import io
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import (
    app,
    get_current_membership,
    get_current_user,
    _rate_limit_store,
)
from app.api import knowledge as api_knowledge
from app.google_drive_client import GoogleDriveFileTooLarge
from app.models import (
    Organization,
    OrganizationMembership,
    User,
    KnowledgeBase,
    KnowledgeSource,
    GoogleOAuthState,
    GoogleConnection,
)

SQLALCHEMY_TEST_DATABASE_URL = (
    "sqlite:///./test_google_sheets.db"
)

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

_user_counter = 0
_org_counter = 0


@pytest.fixture(autouse=True)
def reset_test_state():
    global _user_counter, _org_counter
    _user_counter = 0
    _org_counter = 0
    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()


@pytest.fixture()
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(setup_db):
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_org(db, plan="starter", slug=None):
    global _org_counter
    _org_counter += 1
    o = Organization(
        name=f"Test Org {_org_counter}",
        slug=slug or f"test-org-{_org_counter}",
        plan=plan,
        subscription_status="active",
    )
    db.add(o)
    db.flush()
    return o


def _make_user(db, org, role="owner", email=None):
    global _user_counter
    _user_counter += 1
    email = email or f"user{_user_counter}@test.com"
    u = User(
        email=email,
        name=f"Test User {_user_counter}",
        external_auth_id=f"test-cognito-sub-{_user_counter}",
    )
    db.add(u)
    db.flush()

    m = OrganizationMembership(
        user_id=u.id,
        organization_id=org.id,
        role=role,
    )
    db.add(m)
    db.flush()
    return u, m


def _make_kb(db, org):
    kb = KnowledgeBase(
        organization_id=org.id,
        name="Test KB",
        scope="selected_stores",
        external_id="bedrock-kb-123",
        external_data_source_id="bedrock-ds-456",
        external_status="ready",
    )
    db.add(kb)
    db.flush()
    return kb


@pytest.fixture()
def client_factory(db):
    clients = []

    def _create(org):
        user, membership = _make_user(db, org)

        original_overrides = dict(
            app.dependency_overrides
        )

        def _override_db():
            try:
                yield db
            finally:
                pass

        def _override_user():
            return membership.user

        def _override_membership():
            return membership

        app.dependency_overrides[get_db] = (
            _override_db
        )
        app.dependency_overrides[
            get_current_user
        ] = _override_user
        app.dependency_overrides[
            get_current_membership
        ] = _override_membership

        c = TestClient(
            app,
            raise_server_exceptions=False,
        )
        clients.append(
            (c, original_overrides)
        )
        return c

    yield _create

    for c, overrides in clients:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


# =========================================================
# google_security.py tests
# =========================================================


class TestGoogleSecurity:
    def test_encrypt_decrypt_roundtrip(self):
        from cryptography.fernet import Fernet
        from app.google_security import (
            encrypt_google_secret,
            decrypt_google_secret,
        )

        key = Fernet.generate_key().decode()
        with patch.dict(
            os.environ,
            {"GOOGLE_TOKEN_ENCRYPTION_KEY": key},
        ):
            plaintext = "ya29.test-access-token-123"
            encrypted = encrypt_google_secret(
                plaintext
            )
            assert encrypted != plaintext
            assert encrypted
            decrypted = decrypt_google_secret(
                encrypted
            )
            assert decrypted == plaintext

    def test_encrypt_empty_raises(self):
        from cryptography.fernet import Fernet
        from app.google_security import (
            encrypt_google_secret,
        )

        key = Fernet.generate_key().decode()
        with patch.dict(
            os.environ,
            {"GOOGLE_TOKEN_ENCRYPTION_KEY": key},
        ):
            with pytest.raises(ValueError):
                encrypt_google_secret("")

    def test_decrypt_empty_raises(self):
        from cryptography.fernet import Fernet
        from app.google_security import (
            decrypt_google_secret,
        )

        key = Fernet.generate_key().decode()
        with patch.dict(
            os.environ,
            {"GOOGLE_TOKEN_ENCRYPTION_KEY": key},
        ):
            with pytest.raises(ValueError):
                decrypt_google_secret("")

    def test_missing_env_key_raises(self):
        from app.google_security import (
            encrypt_google_secret,
        )

        env = dict(os.environ)
        env.pop("GOOGLE_TOKEN_ENCRYPTION_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError):
                encrypt_google_secret("test")

    def test_wrong_key_fails_decrypt(self):
        from cryptography.fernet import Fernet
        from app.google_security import (
            encrypt_google_secret,
            decrypt_google_secret,
        )

        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        with patch.dict(
            os.environ,
            {"GOOGLE_TOKEN_ENCRYPTION_KEY": key1},
        ):
            encrypted = encrypt_google_secret(
                "secret"
            )

        with patch.dict(
            os.environ,
            {"GOOGLE_TOKEN_ENCRYPTION_KEY": key2},
        ):
            with pytest.raises(RuntimeError):
                decrypt_google_secret(encrypted)


# =========================================================
# google_sheets_client.py tests
# =========================================================


class TestGoogleSheetsClient:
    def test_extract_from_full_url(self):
        from app.google_sheets_client import (
            extract_spreadsheet_id,
        )

        url = (
            "https://docs.google.com/spreadsheets/"
            "d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=0"
        )
        result = extract_spreadsheet_id(url)
        assert (
            result
            == "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        )

    def test_extract_from_url_no_edit(self):
        from app.google_sheets_client import (
            extract_spreadsheet_id,
        )

        url = (
            "https://docs.google.com/spreadsheets/"
            "d/1AbCdEfGhIjKlMnOpQrStUvWxYz/"
        )
        result = extract_spreadsheet_id(url)
        assert (
            result
            == "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        )

    def test_extract_from_raw_id(self):
        from app.google_sheets_client import (
            extract_spreadsheet_id,
        )

        raw = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        result = extract_spreadsheet_id(raw)
        assert result == raw

    def test_extract_none_returns_none(self):
        from app.google_sheets_client import (
            extract_spreadsheet_id,
        )

        assert (
            extract_spreadsheet_id(None) is None
        )
        assert (
            extract_spreadsheet_id("") is None
        )

    def test_extract_short_string_returns_none(
        self,
    ):
        from app.google_sheets_client import (
            extract_spreadsheet_id,
        )

        assert (
            extract_spreadsheet_id("not-a-id")
            is None
        )

    def test_normalize_to_csv_basic(self):
        from app.google_sheets_client import (
            normalize_to_csv,
        )

        values = [
            ["Name", "Age", "City"],
            ["Alice", "30", "Madrid"],
            ["Bob", "25", "Barcelona"],
        ]
        result = normalize_to_csv(values)

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0] == ["Name", "Age", "City"]
        assert rows[1] == [
            "Alice",
            "30",
            "Madrid",
        ]

    def test_normalize_to_csv_empty(self):
        from app.google_sheets_client import (
            normalize_to_csv,
        )

        assert normalize_to_csv([]) == ""
        assert normalize_to_csv([[]]) == ""

    def test_normalize_to_csv_empty_rows_skipped(
        self,
    ):
        from app.google_sheets_client import (
            normalize_to_csv,
        )

        values = [
            ["Name", "Age"],
            [],
            ["", ""],
            ["Alice", "30"],
        ]
        result = normalize_to_csv(values)

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[1] == ["Alice", "30"]

    def test_normalize_to_csv_pads_columns(self):
        from app.google_sheets_client import (
            normalize_to_csv,
        )

        values = [
            ["A", "B", "C"],
            ["1", "2"],
            ["4", "5", "6"],
        ]
        result = normalize_to_csv(values)

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows[0]) == 3
        assert len(rows[1]) == 3
        assert rows[1][2] == ""

    def test_normalize_to_csv_all_empty_rows(
        self,
    ):
        from app.google_sheets_client import (
            normalize_to_csv,
        )

        values = [
            ["", "", ""],
            ["   ", "", ""],
        ]
        result = normalize_to_csv(values)
        assert result == ""

    @patch(
        "app.google_sheets_client.httpx.AsyncClient"
    )
    def test_fetch_sheet_values_rows(
        self, mock_client_cls
    ):
        from app.google_sheets_client import (
            fetch_sheet_values,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "values": [
                ["H1", "H2"],
                ["a", "b"],
                ["c", "d"],
            ]
        }
        mock_response.raise_for_status = (
            MagicMock()
        )

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(
            return_value=mock_response
        )
        mock_instance.__aenter__ = AsyncMock(
            return_value=mock_instance
        )
        mock_instance.__aexit__ = AsyncMock(
            return_value=False
        )
        mock_client_cls.return_value = (
            mock_instance
        )

        result = asyncio.run(
            fetch_sheet_values(
                "token123", "sheet123", "Sheet1"
            )
        )
        assert len(result) == 3
        assert result[0] == ["H1", "H2"]

    def test_row_limit_exceeded(self):
        from app.google_sheets_client import (
            fetch_sheet_values,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "values": [["x"] * 50 for _ in range(10001)]
        }
        mock_response.raise_for_status = (
            MagicMock()
        )

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(
            return_value=mock_response
        )
        mock_instance.__aenter__ = AsyncMock(
            return_value=mock_instance
        )
        mock_instance.__aexit__ = AsyncMock(
            return_value=False
        )

        with patch(
            "app.google_sheets_client.httpx.AsyncClient",
            return_value=mock_instance,
        ):
            with patch.dict(
                os.environ,
                {
                    "GOOGLE_SHEETS_MAX_ROWS": "10000",
                    "GOOGLE_SHEETS_MAX_COLUMNS": "50",
                    "GOOGLE_SHEETS_MAX_CELLS": "250000",
                },
            ):
                with pytest.raises(ValueError):
                    asyncio.run(
                        fetch_sheet_values(
                            "token",
                            "sheet",
                            "Sheet1",
                        )
                    )


# =========================================================
# bedrock_ingestion.py tests
# =========================================================


class TestBedrockIngestion:
    def test_start_returns_job_id(self):
        from app.bedrock_ingestion import (
            start_ingestion_job,
        )

        mock_client = MagicMock()
        mock_client.start_ingestion_job.return_value = {
            "ingestionJob": {
                "ingestionJobId": "job-abc",
                "status": "STARTING",
            }
        }

        with patch(
            "app.bedrock_ingestion._get_bedrock_agent_client",
            return_value=mock_client,
        ):
            result = start_ingestion_job(
                "kb-123", "ds-456"
            )
            assert result == "job-abc"

    def test_start_missing_ids_returns_none(self):
        from app.bedrock_ingestion import (
            start_ingestion_job,
        )

        result = start_ingestion_job("", "ds-456")
        assert result is None

        result = start_ingestion_job("kb-123", "")
        assert result is None

    def test_start_exception_returns_none(self):
        from app.bedrock_ingestion import (
            start_ingestion_job,
        )

        mock_client = MagicMock()
        mock_client.start_ingestion_job.side_effect = (
            Exception("AWS error")
        )

        with patch(
            "app.bedrock_ingestion._get_bedrock_agent_client",
            return_value=mock_client,
        ):
            result = start_ingestion_job(
                "kb-123", "ds-456"
            )
            assert result is None

    def test_status_complete_returns_synced(self):
        from app.bedrock_ingestion import (
            get_ingestion_status,
        )

        mock_client = MagicMock()
        mock_client.get_ingestion_job.return_value = {
            "ingestionJob": {"status": "COMPLETE"}
        }

        with patch(
            "app.bedrock_ingestion._get_bedrock_agent_client",
            return_value=mock_client,
        ):
            result = get_ingestion_status(
                "kb", "ds", "job"
            )
            assert result == "synced"

    def test_status_failed_returns_failed(self):
        from app.bedrock_ingestion import (
            get_ingestion_status,
        )

        mock_client = MagicMock()
        mock_client.get_ingestion_job.return_value = {
            "ingestionJob": {
                "status": "FAILED",
                "statistics": {},
            }
        }

        with patch(
            "app.bedrock_ingestion._get_bedrock_agent_client",
            return_value=mock_client,
        ):
            result = get_ingestion_status(
                "kb", "ds", "job"
            )
            assert result == "failed"

    def test_status_in_progress_returns_indexing(
        self,
    ):
        from app.bedrock_ingestion import (
            get_ingestion_status,
        )

        mock_client = MagicMock()
        mock_client.get_ingestion_job.return_value = {
            "ingestionJob": {
                "status": "IN_PROGRESS"
            }
        }

        with patch(
            "app.bedrock_ingestion._get_bedrock_agent_client",
            return_value=mock_client,
        ):
            result = get_ingestion_status(
                "kb", "ds", "job"
            )
            assert result == "indexing"

    def test_status_missing_ids_returns_failed(
        self,
    ):
        from app.bedrock_ingestion import (
            get_ingestion_status,
        )

        assert (
            get_ingestion_status("", "ds", "job")
            == "failed"
        )
        assert (
            get_ingestion_status("kb", "", "job")
            == "failed"
        )
        assert (
            get_ingestion_status("kb", "ds", "")
            == "failed"
        )

    def test_status_exception_returns_failed(self):
        from app.bedrock_ingestion import (
            get_ingestion_status,
        )

        mock_client = MagicMock()
        mock_client.get_ingestion_job.side_effect = (
            Exception("AWS error")
        )

        with patch(
            "app.bedrock_ingestion._get_bedrock_agent_client",
            return_value=mock_client,
        ):
            result = get_ingestion_status(
                "kb", "ds", "job"
            )
            assert result == "failed"

    def test_map_google_api_error_401(self):
        from app.bedrock_ingestion import (
            map_google_api_error,
        )

        code, msg = map_google_api_error(401)
        assert code == "reconnect_required"
        assert "expired" in msg.lower()

    def test_map_google_api_error_403(self):
        from app.bedrock_ingestion import (
            map_google_api_error,
        )

        code, msg = map_google_api_error(403)
        assert code == "permission_denied"

    def test_map_google_api_error_404(self):
        from app.bedrock_ingestion import (
            map_google_api_error,
        )

        code, msg = map_google_api_error(404)
        assert code == "not_found"

    def test_map_google_api_error_429(self):
        from app.bedrock_ingestion import (
            map_google_api_error,
        )

        code, msg = map_google_api_error(429)
        assert code == "rate_limited"

    def test_map_google_api_error_500(self):
        from app.bedrock_ingestion import (
            map_google_api_error,
        )

        code, msg = map_google_api_error(500)
        assert code == "provider_error"

    def test_map_google_api_error_unknown(self):
        from app.bedrock_ingestion import (
            map_google_api_error,
        )

        code, msg = map_google_api_error(418)
        assert code == "unknown_error"


# =========================================================
# API endpoint tests
# =========================================================


class TestGoogleStatusEndpoint:
    def test_not_connected(self, client_factory, db):
        org = _make_org(db)
        client = client_factory(org)

        resp = client.get(
            "/api/integrations/google/status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["email"] is None

    def test_connected(self, client_factory, db):
        org = _make_org(db)
        user, _ = _make_user(db, org)

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            refresh_token_encrypted="enc-refresh",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        resp = client.get(
            "/api/integrations/google/status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["email"] == "test@gmail.com"


class TestGoogleOAuthStart:
    def test_start_returns_url(
        self, client_factory, db
    ):
        org = _make_org(db)
        client = client_factory(org)

        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_CLIENT_SECRET": "test-secret",
                "GOOGLE_REDIRECT_URI": "https://api.diaglob.tech/api/integrations/google/oauth/callback",
            },
        ):
            resp = client.get(
                "/api/integrations/google/oauth/start"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "authorization_url" in data
        assert "accounts.google.com" in data[
            "authorization_url"
        ]


class TestGoogleDisconnect:
    def test_disconnect(self, client_factory, db):
        org = _make_org(db)
        user, _ = _make_user(db, org)

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            refresh_token_encrypted="enc-refresh",
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        with patch(
            "app.api.google.decrypt_google_secret",
            return_value="decrypted-token",
        ):
            with patch(
                "app.api.google.httpx"
            ) as mock_httpx:
                mock_httpx.post = MagicMock(
                    return_value=MagicMock(
                        status_code=200
                    )
                )
                resp = client.delete(
                    "/api/integrations/google"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "revoked"


class TestGoogleSheetsList:
    def test_list_sheets(self, client_factory, db):
        org = _make_org(db)
        user, _ = _make_user(db, org)

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        mock_drive_resp = MagicMock()
        mock_drive_resp.json.return_value = {
            "files": [
                {
                    "id": "sheet-123",
                    "name": "My Sheet",
                    "modifiedTime": "2025-01-01T00:00:00Z",
                }
            ]
        }
        mock_drive_resp.raise_for_status = (
            MagicMock()
        )

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(
            return_value=mock_drive_resp
        )

        with patch(
            "app.api.google._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.api.google.httpx.AsyncClient"
            ) as mock_httpx:
                mock_httpx.return_value.__aenter__ = (
                    AsyncMock(
                        return_value=mock_instance
                    )
                )
                mock_httpx.return_value.__aexit__ = (
                    AsyncMock(return_value=False)
                )
                resp = client.get(
                    "/api/integrations/google/sheets"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sheets"]) == 1
        assert (
            data["sheets"][0]["name"] == "My Sheet"
        )

    def test_not_connected_returns_404(
        self, client_factory, db
    ):
        org = _make_org(db)
        client = client_factory(org)

        resp = client.get(
            "/api/integrations/google/sheets"
        )
        assert resp.status_code == 404


class TestGoogleSheetTabs:
    def test_list_tabs(self, client_factory, db):
        org = _make_org(db)
        user, _ = _make_user(db, org)

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        mock_sheets_resp = MagicMock()
        mock_sheets_resp.json.return_value = {
            "properties": {
                "title": "My Spreadsheet"
            },
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "index": 0,
                    }
                },
                {
                    "properties": {
                        "sheetId": 1,
                        "title": "Data",
                        "index": 1,
                    }
                },
            ],
        }
        mock_sheets_resp.raise_for_status = (
            MagicMock()
        )

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(
            return_value=mock_sheets_resp
        )

        with patch(
            "app.api.google._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.api.google.httpx.AsyncClient"
            ) as mock_httpx:
                mock_httpx.return_value.__aenter__ = (
                    AsyncMock(
                        return_value=mock_instance
                    )
                )
                mock_httpx.return_value.__aexit__ = (
                    AsyncMock(return_value=False)
                )
                resp = client.get(
                    "/api/integrations/google/sheets/sheet-123/tabs"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tabs"]) == 2
        assert (
            data["tabs"][0]["title"] == "Sheet1"
        )


class TestAddGoogleSheetSource:
    def test_workbook_content_uses_visible_non_empty_tabs(self):
        from app.services.google_sheet_sources import _fetch_google_workbook_content

        metadata = {
            "title": "Operations",
            "sheets": [
                {"title": "Orders", "hidden": False},
                {"title": "Empty", "hidden": False},
                {"title": "Internal", "hidden": True},
            ],
        }

        async def values(_token, _spreadsheet_id, tab_name):
            return {
                "Orders": [["Order", "Total"], ["A-1", "10"]],
                "Empty": [],
            }[tab_name]

        with patch(
            "app.services.google_sheet_sources.get_spreadsheet_metadata",
            AsyncMock(return_value=metadata),
        ), patch(
            "app.services.google_sheet_sources.fetch_sheet_values",
            AsyncMock(side_effect=values),
        ) as fetch_values:
            title, content = asyncio.run(
                _fetch_google_workbook_content("token", "sheet-id", "Fallback")
            )

        assert title == "Operations"
        assert content == (
            "# Spreadsheet: Operations\n\n"
            "## Sheet: Orders\nOrder,Total\nA-1,10\n"
        )
        assert [call.args[2] for call in fetch_values.call_args_list] == [
            "Orders", "Empty"
        ]

    def test_workbook_content_rejects_only_empty_visible_tabs(self):
        from app.services.google_sheet_sources import _fetch_google_workbook_content

        with patch(
            "app.services.google_sheet_sources.get_spreadsheet_metadata",
            AsyncMock(return_value={
                "title": "Empty Book",
                "sheets": [{"title": "Empty", "hidden": False}],
            }),
        ), patch(
            "app.services.google_sheet_sources.fetch_sheet_values",
            AsyncMock(return_value=[]),
        ):
            with pytest.raises(
                ValueError,
                match="no non-empty visible sheets",
            ):
                asyncio.run(
                    _fetch_google_workbook_content(
                        "token", "sheet-id", "Fallback"
                    )
                )

    def test_add_workbook_source_persists_import_mode(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        connection = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow() + timedelta(hours=1),
            status="connected",
        )
        db.add(connection)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token", return_value="token"
        ), patch(
            "app.services.google_sheet_sources._fetch_google_workbook_content",
            AsyncMock(return_value=(
                "Operations",
                "# Spreadsheet: Operations\n\n## Sheet: Data\nName\nAlice\n",
            )),
        ), patch(
            "app.services.google_sheet_sources.upload_knowledge_file",
            return_value={"bucket": "bucket", "key": "workbook-key"},
        ), patch(
            "app.services.google_sheet_sources.start_ingestion_job", return_value="job-workbook"
        ):
            resp = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/google-sheet",
                json={
                    "spreadsheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz",
                    "import_mode": "workbook",
                },
            )

        assert resp.status_code == 200
        source = db.get(KnowledgeSource, resp.json()["source_id"])
        assert source.sheet_name is None
        assert source.metadata_json == '{"import_mode": "workbook"}'

    def test_add_workbook_requires_ready_knowledge_base(
        self, client_factory, db
    ):
        org = _make_org(db)
        kb = _make_kb(db, org)
        kb.external_status = "provisioning"
        db.commit()
        client = client_factory(org)

        resp = client.post(
            f"/api/knowledge-bases/{kb.id}/sources/google-sheet",
            json={
                "spreadsheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz",
                "import_mode": "workbook",
            },
        )

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "KNOWLEDGE_BASE_NOT_READY"

    def test_add_source_starts_ingestion(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        mock_sheets_resp = MagicMock()
        mock_sheets_resp.json.return_value = {
            "properties": {
                "title": "My Spreadsheet"
            },
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "index": 0,
                    }
                }
            ],
        }
        mock_sheets_resp.raise_for_status = (
            MagicMock()
        )

        mock_values_resp = MagicMock()
        mock_values_resp.json.return_value = {
            "values": [
                ["Name", "Age"],
                ["Alice", "30"],
            ]
        }
        mock_values_resp.raise_for_status = (
            MagicMock()
        )

        async def mock_get(url, **kwargs):
            if "values" in str(url):
                return mock_values_resp
            return mock_sheets_resp

        mock_instance = AsyncMock()
        mock_instance.get = mock_get

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.api.knowledge.httpx.AsyncClient"
            ) as mock_httpx:
                mock_httpx.return_value.__aenter__ = (
                    AsyncMock(
                        return_value=mock_instance
                    )
                )
                mock_httpx.return_value.__aexit__ = (
                    AsyncMock(return_value=False)
                )
                with patch(
                    "app.services.google_sheet_sources.upload_knowledge_file"
                ) as mock_upload:
                    mock_upload.return_value = {
                        "bucket": "diaglob-bucket",
                        "key": "google/sheet-key/Sheet1.csv",
                    }
                    with patch(
                        "app.services.google_sheet_sources.start_ingestion_job",
                        return_value="job-789",
                    ):
                        resp = client.post(
                            f"/api/knowledge-bases/{kb.id}/sources/google-sheet",
                            json={
                                "spreadsheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz",
                                "spreadsheet_name": "My Spreadsheet",
                                "sheet_name": "Sheet1",
                            },
                        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_status"] == "indexing"
        assert data["source_id"] is not None

    def test_duplicate_source_returns_existing(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"

        existing_source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="My Spreadsheet - Sheet1",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/Sheet1.csv",
            status="active",
            external_id=sheet_id,
            external_name="My Spreadsheet",
            sheet_name="Sheet1",
            sync_status="synced",
        )
        db.add(existing_source)
        db.commit()

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        resp = client.post(
            f"/api/knowledge-bases/{kb.id}/sources/google-sheet",
            json={
                "spreadsheet_id": sheet_id,
                "spreadsheet_name": "My Spreadsheet",
                "sheet_name": "Sheet1",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_status"] == "synced"
        assert (
            data["source_id"] == existing_source.id
        )

    def test_duplicate_workbook_returns_existing(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="My Spreadsheet",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/workbook.csv",
            status="active",
            external_id=sheet_id,
            external_name="My Spreadsheet",
            sheet_name=None,
            sync_status="synced",
            metadata_json='{"import_mode": "workbook"}',
        )
        db.add(source)
        db.commit()
        client = client_factory(org)

        with patch("app.services.google_sheet_sources._fetch_google_workbook_content") as fetch:
            resp = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/google-sheet",
                json={
                    "spreadsheet_id": sheet_id,
                    "import_mode": "workbook",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["source_id"] == source.id
        fetch.assert_not_called()


class TestSyncGoogleSheetSource:
    def test_sync_workbook(self, client_factory, db):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="Old Workbook Name",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/workbook.csv",
            status="active",
            external_id="1AbCdEfGhIjKlMnOpQrStUvWxYz",
            external_name="Old Workbook Name",
            sheet_name=None,
            sync_status="synced",
            metadata_json='{"import_mode": "workbook"}',
        )
        connection = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow() + timedelta(hours=1),
            status="connected",
        )
        db.add_all([source, connection])
        db.commit()
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="valid-token",
        ), patch(
            "app.services.google_sheet_sources._fetch_google_workbook_content",
            AsyncMock(return_value=(
                "New Workbook Name",
                "# Spreadsheet: New Workbook Name\n\n"
                "## Sheet: Data\nName\nAlice\n",
            )),
        ), patch(
            "app.services.google_sheet_sources.upload_knowledge_file",
            return_value={"bucket": "diaglob-bucket", "key": "new-key"},
        ) as upload, patch(
            "app.services.google_sheet_sources.start_ingestion_job", return_value="job-workbook"
        ):
            resp = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/{source.id}/sync"
            )

        assert resp.status_code == 200
        assert resp.json()["sync_status"] == "indexing"
        assert upload.call_args.kwargs["filename"].endswith("_workbook.csv")
        db.refresh(source)
        assert source.external_name == "New Workbook Name"

    def test_sync_existing_source(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"

        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="My Spreadsheet - Sheet1",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/Sheet1.csv",
            status="active",
            external_id=sheet_id,
            external_name="My Spreadsheet",
            sheet_name="Sheet1",
            sync_status="synced",
        )
        db.add(source)
        db.commit()

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        mock_values_resp = MagicMock()
        mock_values_resp.json.return_value = {
            "values": [
                ["Name", "Age"],
                ["Alice", "30"],
            ]
        }
        mock_values_resp.raise_for_status = (
            MagicMock()
        )

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(
            return_value=mock_values_resp
        )

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.api.knowledge.httpx.AsyncClient"
            ) as mock_httpx:
                mock_httpx.return_value.__aenter__ = (
                    AsyncMock(
                        return_value=mock_instance
                    )
                )
                mock_httpx.return_value.__aexit__ = (
                    AsyncMock(return_value=False)
                )
                with patch(
                    "app.services.google_sheet_sources.upload_knowledge_file"
                ) as mock_upload:
                    mock_upload.return_value = {
                        "bucket": "diaglob-bucket",
                        "key": "google/sheet-key/Sheet1.csv",
                    }
                    with patch(
                        "app.services.google_sheet_sources.start_ingestion_job",
                        return_value="job-new",
                    ):
                        resp = client.post(
                            f"/api/knowledge-bases/{kb.id}/sources/{source.id}/sync",
                        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_status"] == "indexing"

    def test_sync_already_indexing_returns_current_status(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"

        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="My Spreadsheet - Sheet1",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/Sheet1.csv",
            status="active",
            external_id=sheet_id,
            external_name="My Spreadsheet",
            sheet_name="Sheet1",
            sync_status="indexing",
        )
        db.add(source)
        db.commit()

        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            email="test@gmail.com",
            access_token_encrypted="enc-access",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn)
        db.commit()

        client = client_factory(org)

        resp = client.post(
            f"/api/knowledge-bases/{kb.id}/sources/{source.id}/sync",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_status"] == "indexing"
        assert (
            data["message"]
            == "Sync already in progress"
        )


class TestIngestionStatusEndpoint:
    def test_get_status(self, client_factory, db):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="My Spreadsheet - Sheet1",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/Sheet1.csv",
            status="active",
            external_id="sheet-123",
            external_name="My Spreadsheet",
            sheet_name="Sheet1",
            sync_status="synced",
            last_synced_at=datetime.utcnow(),
        )
        db.add(source)
        db.commit()

        client = client_factory(org)

        resp = client.get(
            f"/api/knowledge-bases/{kb.id}/sources/{source.id}/ingestion-status",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_status"] == "synced"
        assert data["source_id"] == source.id


# =========================================================
# Tenant isolation tests
# =========================================================


class TestTenantIsolation:
    def test_org_a_cannot_access_org_b_sheets(
        self, client_factory, db
    ):
        org_a = _make_org(db)
        org_b = _make_org(db)

        user_b, _ = _make_user(db, org_b)

        conn_b = GoogleConnection(
            organization_id=org_b.id,
            user_id=user_b.id,
            email="orgb@gmail.com",
            access_token_encrypted="enc-access-b",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn_b)
        db.commit()

        client_a = client_factory(org_a)

        resp = client_a.get(
            "/api/integrations/google/sheets"
        )
        assert resp.status_code == 404

    def test_org_a_cannot_add_source_to_org_b_kb(
        self, client_factory, db
    ):
        org_a = _make_org(db)
        org_b = _make_org(db)

        user_b, _ = _make_user(db, org_b)

        kb_b = _make_kb(db, org_b)

        conn_b = GoogleConnection(
            organization_id=org_b.id,
            user_id=user_b.id,
            email="orgb@gmail.com",
            access_token_encrypted="enc-access-b",
            token_expiry=datetime.utcnow()
            + timedelta(hours=1),
            status="connected",
        )
        db.add(conn_b)
        db.commit()

        client_a = client_factory(org_a)

        resp = client_a.post(
            f"/api/knowledge-bases/{kb_b.id}/sources/google-sheet",
            json={
                "spreadsheet_id": "sheet-123",
                "spreadsheet_name": "Sheet",
                "sheet_name": "Tab1",
            },
        )

        assert resp.status_code == 404


# =========================================================
# DELETE + BEDROCK REINDEX TESTS
# =========================================================


class TestDeleteSourceBedrockReindex:
    def _connection(self, db, org, user, scopes):
        connection = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            access_token_encrypted="enc-access",
            refresh_token_encrypted="enc-refresh",
            token_expiry=datetime.utcnow() + timedelta(hours=1),
            scopes=scopes,
            status="connected",
        )
        db.add(connection)
        db.commit()
        return connection

    def test_google_source_delete_triggers_reindex(
        self, client_factory, db
    ):
        """A. Google source delete → S3 delete + StartIngestionJob"""
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="Test Sheet - Sheet1",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/Sheet1.csv",
            status="active",
            external_id="1AbCdEfGhIjKlMnOpQrStUvWxYz",
            external_name="Test Sheet",
            sheet_name="Sheet1",
            sync_status="synced",
        )
        db.add(source)
        db.commit()

        client = client_factory(org)

        with patch(
            "app.services.knowledge_source_lifecycle.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.services.knowledge_ingestion.start_ingestion_job",
            return_value="job-cleanup-123",
        ) as mock_ingest:
            resp = client.delete(
                f"/api/knowledge-bases/{kb.id}/sources/{source.id}",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["reindex_status"] == "indexing"
        assert data["ingestion_job_id"] == "job-cleanup-123"
        mock_delete.assert_called_once_with(
            "diaglob-bucket",
            "google/sheet-123/Sheet1.csv",
        )
        mock_ingest.assert_called_once_with(
            "bedrock-kb-123",
            "bedrock-ds-456",
        )

    def test_modified_upload_failure_preserves_old_artifact(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        source = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Policies.pdf",
            source_type="google_drive_file",
            content_type="application/pdf",
            s3_bucket="bucket",
            s3_key="old-key",
            external_id="file-1",
            external_name="Policies.pdf",
            external_mime_type="application/pdf",
            status="uploaded",
            sync_status="synced",
        )
        db.add(source)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.services.drive_file_sources.download_drive_file",
            return_value=b"new-content",
        ), patch(
            "app.services.drive_file_sources.upload_knowledge_file",
            side_effect=RuntimeError("upload unavailable"),
        ), patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ) as delete_file:
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{source.id}/sync-drive-file"
            )

        assert response.status_code == 500
        delete_file.assert_not_called()
        db.refresh(source)
        assert source.s3_bucket == "bucket"
        assert source.s3_key == "old-key"
        assert source.sync_status == "failed"

    def test_new_artifact_cleaned_on_db_persistence_failure(
        self,
    ):
        from app.services.knowledge_sources import _persist_new_drive_source

        fake_db = MagicMock()
        fake_db.commit.side_effect = RuntimeError("db down")
        source = MagicMock()
        uploaded = {"bucket": "bucket", "key": "new-key"}

        with patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ) as delete_file:
            with pytest.raises(RuntimeError, match="db down"):
                _persist_new_drive_source(
                    fake_db, source, uploaded
                )

        fake_db.rollback.assert_called_once()
        delete_file.assert_called_once_with(
            "bucket", "new-key"
        )

    def test_folder_partial_failure_summary_and_status(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Folder",
            source_type="google_drive_folder",
            s3_bucket="",
            s3_key="",
            external_id="folder-1",
            status="uploaded",
            sync_status="synced",
        )
        db.add(folder)
        db.commit()
        client = client_factory(org)
        files = [
            {
                "id": "new-1", "name": "One.pdf",
                "mimeType": "application/pdf", "size": "3",
                "modifiedTime": "2026-08-31T10:00:00Z",
            },
            {
                "id": "new-2", "name": "Two.pdf",
                "mimeType": "application/pdf", "size": "3",
                "modifiedTime": "2026-08-31T10:00:00Z",
            },
        ]

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.services.knowledge_sources.list_folder_children",
            return_value={"files": files},
        ), patch(
            "app.services.knowledge_sources._download_drive_child",
            side_effect=[
                (b"one", "application/pdf", "google_drive_file"),
                RuntimeError("download failed"),
            ],
        ), patch(
            "app.services.knowledge_sources.upload_knowledge_file",
            return_value={"bucket": "bucket", "key": "new-1"},
        ), patch(
            "app.services.knowledge_sources.start_ingestion_job",
            return_value="job-1",
        ) as start_job:
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{folder.id}/sync-folder"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["sync_status"] == "partial_failed"
        assert data["summary"]["new"] == 1
        assert data["summary"]["successful_delta"] is True
        assert data["summary"]["failed"][0]["id"] == "new-2"
        start_job.assert_called_once()

    def test_removed_delete_failure_stays_active_without_delta(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Folder",
            source_type="google_drive_folder",
            s3_bucket="", s3_key="", external_id="folder-1",
            status="uploaded", sync_status="synced",
        )
        db.add(folder)
        db.flush()
        child = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            parent_source_id=folder.id,
            name="Gone.pdf",
            source_type="google_drive_file",
            s3_bucket="bucket", s3_key="old-key",
            external_id="gone-1", status="uploaded",
            sync_status="synced",
        )
        db.add(child)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.services.knowledge_sources.list_folder_children",
            return_value={"files": []},
        ), patch(
            "app.services.knowledge_sources.delete_knowledge_file",
            side_effect=RuntimeError("delete denied"),
        ), patch(
            "app.services.knowledge_sources.start_ingestion_job"
        ) as start_job:
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{folder.id}/sync-folder"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["sync_status"] == "failed"
        assert data["summary"]["removed"] == 0
        assert data["summary"]["successful_delta"] is False
        start_job.assert_not_called()
        db.refresh(child)
        assert child.active is True
        assert child.sync_status == "failed"

    def test_single_sync_without_bedrock_ids_is_rejected(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = KnowledgeBase(
            organization_id=org.id,
            name="No Bedrock",
            scope="selected_stores",
            external_id=None,
            external_data_source_id=None,
        )
        db.add(kb)
        db.flush()
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        source = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="File.pdf",
            source_type="google_drive_file",
            content_type="application/pdf",
            s3_bucket="bucket", s3_key="old-key",
            external_id="file-1", external_name="File.pdf",
            external_mime_type="application/pdf",
            status="uploaded", sync_status="synced",
        )
        db.add(source)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.services.drive_file_sources.download_drive_file",
            return_value=b"new",
        ), patch(
            "app.services.drive_file_sources.get_file_metadata",
            return_value={},
        ), patch(
            "app.services.drive_file_sources.upload_knowledge_file",
            return_value={"bucket": "bucket", "key": "new-key"},
        ), patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ), patch(
            "app.services.knowledge_sources.start_ingestion_job"
        ) as start_job:
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{source.id}/sync-drive-file"
            )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == (
            "KNOWLEDGE_BASE_NOT_READY"
        )
        start_job.assert_not_called()
        db.refresh(source)
        assert source.s3_key == "old-key"
        assert source.sync_status == "synced"

    @pytest.mark.parametrize(
        "start_error",
        [None, RuntimeError("bedrock unavailable")],
    )
    def test_single_ingestion_start_failure_stays_uploaded(
        self, start_error, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        source = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="File.pdf", source_type="google_drive_file",
            content_type="application/pdf",
            s3_bucket="bucket", s3_key="old-key",
            external_id="file-1", external_name="File.pdf",
            external_mime_type="application/pdf",
            status="uploaded", sync_status="synced",
        )
        db.add(source)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token", return_value="token"
        ), patch(
            "app.services.drive_file_sources.download_drive_file", return_value=b"new"
        ), patch(
            "app.services.drive_file_sources.get_file_metadata", return_value={}
        ), patch(
            "app.services.drive_file_sources.upload_knowledge_file",
            return_value={"bucket": "bucket", "key": "new-key"},
        ), patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ), patch(
            "app.services.knowledge_sources.start_ingestion_job"
        ) as start_job:
            if start_error is None:
                start_job.return_value = None
            else:
                start_job.side_effect = start_error
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{source.id}/sync-drive-file"
            )

        assert response.status_code == 200
        assert response.json()["sync_status"] == "uploaded"
        assert "failed to start" in response.json()[
            "sync_error"
        ].lower()
        db.refresh(source)
        assert source.sync_status == "uploaded"
        assert source.sync_error

    def test_folder_zero_delta_starts_no_ingestion(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Folder", source_type="google_drive_folder",
            s3_bucket="", s3_key="", external_id="folder-1",
            status="uploaded", sync_status="synced",
        )
        db.add(folder)
        db.flush()
        modified = datetime(2026, 8, 31, 10, 0, 0)
        child = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            parent_source_id=folder.id,
            name="Same.pdf", source_type="google_drive_file",
            s3_bucket="bucket", s3_key="same-key",
            external_id="same-1", status="uploaded",
            sync_status="synced", external_modified_at=modified,
        )
        db.add(child)
        db.commit()
        client = client_factory(org)
        files = [{
            "id": "same-1", "name": "Same.pdf",
            "mimeType": "application/pdf", "size": "3",
            "modifiedTime": "2026-08-31T10:00:00Z",
        }]

        with patch(
            "app.api.knowledge._get_valid_google_token", return_value="token"
        ), patch(
            "app.services.knowledge_sources.list_folder_children",
            return_value={"files": files},
        ), patch(
            "app.services.knowledge_sources.start_ingestion_job"
        ) as start_job, patch(
            "app.services.knowledge_sources._download_drive_child"
        ) as download:
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{folder.id}/sync-folder"
            )

        assert response.status_code == 200
        assert response.json()["sync_status"] == "synced"
        assert response.json()["summary"]["unchanged"] == 1
        assert response.json()["summary"]["successful_delta"] is False
        start_job.assert_not_called()
        download.assert_not_called()

    def test_mixed_folder_delta_starts_exactly_one_job(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Folder", source_type="google_drive_folder",
            s3_bucket="", s3_key="", external_id="folder-1",
            status="uploaded", sync_status="synced",
        )
        db.add(folder)
        db.flush()
        modified_child = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            parent_source_id=folder.id,
            name="Changed.pdf", source_type="google_drive_file",
            s3_bucket="bucket", s3_key="modified-old",
            external_id="modified-1", status="uploaded",
            sync_status="synced",
            external_modified_at=datetime(2026, 8, 30),
        )
        removed_child = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            parent_source_id=folder.id,
            name="Removed.pdf", source_type="google_drive_file",
            s3_bucket="bucket", s3_key="removed-old",
            external_id="removed-1", status="uploaded",
            sync_status="synced",
        )
        db.add_all([modified_child, removed_child])
        db.commit()
        client = client_factory(org)
        files = [
            {
                "id": "new-1", "name": "New.pdf",
                "mimeType": "application/pdf", "size": "3",
                "modifiedTime": "2026-08-31T10:00:00Z",
            },
            {
                "id": "modified-1", "name": "Changed.pdf",
                "mimeType": "application/pdf", "size": "4",
                "modifiedTime": "2026-08-31T10:00:00Z",
            },
        ]

        with patch(
            "app.api.knowledge._get_valid_google_token", return_value="token"
        ), patch(
            "app.services.knowledge_sources.list_folder_children",
            return_value={"files": files},
        ), patch(
            "app.services.knowledge_sources._download_drive_child",
            side_effect=[
                (b"new", "application/pdf", "google_drive_file"),
                (b"changed", "application/pdf", "google_drive_file"),
            ],
        ), patch(
            "app.services.knowledge_sources.upload_knowledge_file",
            side_effect=[
                {"bucket": "bucket", "key": "new-key"},
                {"bucket": "bucket", "key": "modified-new"},
            ],
        ), patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ), patch(
            "app.services.knowledge_sources.start_ingestion_job",
            return_value="job-mixed",
        ) as start_job:
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{folder.id}/sync-folder"
            )

        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["new"] == 1
        assert summary["modified"] == 1
        assert summary["removed"] == 1
        assert response.json()["sync_status"] == "indexing"
        start_job.assert_called_once_with(
            "bedrock-kb-123", "bedrock-ds-456"
        )

    def test_folder_conflicts_are_detected_before_download(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        old_folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Old", source_type="google_drive_folder",
            s3_bucket="", s3_key="", external_id="old-folder",
            status="uploaded", sync_status="synced",
        )
        db.add(old_folder)
        db.flush()
        existing_child = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            parent_source_id=old_folder.id,
            name="Duplicate.pdf", source_type="google_drive_file",
            s3_bucket="bucket", s3_key="existing-key",
            external_id="duplicate-1", status="uploaded",
            sync_status="synced",
        )
        db.add(existing_child)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.services.drive_file_sources.download_drive_file"
        ) as download, patch(
            "app.services.drive_file_sources.upload_knowledge_file"
        ) as upload:
            standalone = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                "google-drive-file",
                json={
                    "file_id": "duplicate-1",
                    "file_name": "Duplicate.pdf",
                    "mime_type": "application/pdf",
                },
            )
        assert standalone.status_code == 409
        download.assert_not_called()
        upload.assert_not_called()

        files = [{
            "id": "duplicate-1", "name": "Duplicate.pdf",
            "mimeType": "application/pdf", "size": "3",
        }]
        with patch(
            "app.api.knowledge._get_valid_google_token", return_value="token"
        ), patch(
            "app.services.knowledge_sources.list_folder_children",
            return_value={"files": files},
        ), patch(
            "app.services.knowledge_sources._download_drive_child"
        ) as download, patch(
            "app.services.knowledge_sources.upload_knowledge_file"
        ) as upload, patch(
            "app.services.knowledge_sources.start_ingestion_job"
        ) as start_job:
            folder_response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                "google-drive-folder",
                json={
                    "folder_id": "new-folder",
                    "folder_name": "New",
                },
            )

        assert folder_response.status_code == 200
        assert folder_response.json()["summary"]["ignored"][0][
            "id"
        ] == "duplicate-1"
        download.assert_not_called()
        upload.assert_not_called()
        start_job.assert_not_called()

    def test_folder_listing_failure_performs_no_removals(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Folder", source_type="google_drive_folder",
            s3_bucket="", s3_key="", external_id="folder-1",
            status="uploaded", sync_status="synced",
        )
        db.add(folder)
        db.flush()
        child = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            parent_source_id=folder.id,
            name="Keep.pdf", source_type="google_drive_file",
            s3_bucket="bucket", s3_key="keep-key",
            external_id="keep-1", status="uploaded",
            sync_status="synced",
        )
        db.add(child)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token", return_value="token"
        ), patch(
            "app.services.knowledge_sources.list_folder_children",
            side_effect=RuntimeError("repeated page token"),
        ), patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ) as delete_file, patch(
            "app.services.knowledge_sources.start_ingestion_job"
        ) as start_job:
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                f"{folder.id}/sync-folder"
            )

        assert response.status_code == 502
        delete_file.assert_not_called()
        start_job.assert_not_called()
        db.refresh(folder)
        db.refresh(child)
        assert folder.sync_status == "failed"
        assert child.active is True

    def test_actual_cumulative_bytes_include_google_docs(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(
            db, org, user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        client = client_factory(org)
        files = [
            {
                "id": "doc-1", "name": "Doc",
                "mimeType": "application/vnd.google-apps.document",
                "size": "0",
            },
            {
                "id": "file-1", "name": "File.pdf",
                "mimeType": "application/pdf", "size": "1",
            },
        ]

        with patch(
            "app.services.knowledge_sources.MAX_TOTAL_SYNC_BYTES", 5
        ), patch(
            "app.api.knowledge._get_valid_google_token", return_value="token"
        ), patch(
            "app.services.knowledge_sources.list_folder_children",
            return_value={"files": files},
        ), patch(
            "app.services.knowledge_sources.export_google_doc", return_value=b"1234"
        ) as export_doc, patch(
            "app.services.knowledge_sources.download_drive_file", return_value=b"5678"
        ), patch(
            "app.services.knowledge_sources.upload_knowledge_file",
            return_value={"bucket": "bucket", "key": "doc-key"},
        ) as upload, patch(
            "app.services.knowledge_sources.start_ingestion_job", return_value="job-1"
        ):
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/"
                "google-drive-folder",
                json={"folder_id": "folder-1", "folder_name": "Folder"},
            )

        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["new"] == 1
        assert summary["failed"][0]["id"] == "file-1"
        assert "Actual downloaded" in summary["failed"][0]["error"]
        export_doc.assert_awaited_once()
        upload.assert_called_once()

    def test_folder_delete_failure_leaves_all_sources_active(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Folder", source_type="google_drive_folder",
            s3_bucket="", s3_key="", external_id="folder-1",
            status="uploaded", sync_status="synced",
        )
        db.add(folder)
        db.flush()
        children = [
            KnowledgeSource(
                organization_id=org.id,
                knowledge_base_id=kb.id,
                parent_source_id=folder.id,
                name=f"Child {index}",
                source_type="google_drive_file",
                s3_bucket="bucket", s3_key=f"key-{index}",
                external_id=f"file-{index}", status="uploaded",
                sync_status="synced",
            )
            for index in range(2)
        ]
        db.add_all(children)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.services.knowledge_sources.delete_knowledge_file",
            side_effect=[None, RuntimeError("delete failed")],
        ), patch(
            "app.services.knowledge_ingestion.start_ingestion_job"
        ) as start_job:
            response = client.delete(
                f"/api/knowledge-bases/{kb.id}/sources/{folder.id}"
            )

        assert response.status_code == 502
        start_job.assert_not_called()
        db.expire_all()
        assert db.get(KnowledgeSource, folder.id).active is True
        assert all(
            db.get(KnowledgeSource, child.id).active is True
            for child in children
        )

    def test_cross_tenant_drive_syncs_have_no_side_effects(
        self, client_factory, db
    ):
        org_a = _make_org(db)
        org_b = _make_org(db)
        kb_b = _make_kb(db, org_b)
        folder = KnowledgeSource(
            organization_id=org_b.id,
            knowledge_base_id=kb_b.id,
            name="Folder", source_type="google_drive_folder",
            s3_bucket="", s3_key="", external_id="folder-b",
            status="uploaded", sync_status="synced",
        )
        file_source = KnowledgeSource(
            organization_id=org_b.id,
            knowledge_base_id=kb_b.id,
            name="File.pdf", source_type="google_drive_file",
            content_type="application/pdf",
            s3_bucket="bucket", s3_key="key-b",
            external_id="file-b", status="uploaded",
            sync_status="synced",
        )
        db.add_all([folder, file_source])
        db.commit()
        client = client_factory(org_a)

        with patch(
            "app.services.knowledge_sources.list_folder_children"
        ) as list_children, patch(
            "app.services.drive_file_sources.download_drive_file"
        ) as download, patch(
            "app.services.drive_file_sources.upload_knowledge_file"
        ) as upload, patch(
            "app.services.knowledge_sources.start_ingestion_job"
        ) as start_job:
            folder_response = client.post(
                f"/api/knowledge-bases/{kb_b.id}/sources/"
                f"{folder.id}/sync-folder"
            )
            file_response = client.post(
                f"/api/knowledge-bases/{kb_b.id}/sources/"
                f"{file_source.id}/sync-drive-file"
            )

        assert folder_response.status_code == 404
        assert file_response.status_code == 404
        list_children.assert_not_called()
        download.assert_not_called()
        upload.assert_not_called()
        start_job.assert_not_called()


class TestGoogleOAuthCallbackCorrectness:
    def test_failed_exchange_consumes_state(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        state = GoogleOAuthState(
            state_token="state-failed-exchange",
            organization_id=org.id,
            user_id=user.id,
            scopes="scope-a",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            used=False,
        )
        db.add(state)
        db.commit()
        client = client_factory(org)

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
        }), patch(
            "app.api.google.httpx.post",
            side_effect=RuntimeError("exchange failed"),
        ):
            first = client.get(
                "/api/integrations/google/oauth/callback",
                params={
                    "code": "bad-code",
                    "state": state.state_token,
                },
                follow_redirects=False,
            )
            second = client.get(
                "/api/integrations/google/oauth/callback",
                params={
                    "code": "bad-code",
                    "state": state.state_token,
                },
                follow_redirects=False,
            )

        assert first.status_code == 302
        assert second.status_code == 400
        db.refresh(state)
        assert state.used is True

    def test_incremental_callback_uses_state_org_and_merges_scopes(
        self, client_factory, db
    ):
        org_a = _make_org(db)
        org_b = _make_org(db)
        user_a, _ = _make_user(db, org_a)
        user_b, _ = _make_user(db, org_b)
        sheets_scope = (
            "https://www.googleapis.com/auth/"
            "spreadsheets.readonly"
        )
        drive_scope = (
            "https://www.googleapis.com/auth/drive.readonly"
        )
        connection_a = GoogleConnection(
            organization_id=org_a.id,
            user_id=user_a.id,
            access_token_encrypted="old-a",
            refresh_token_encrypted="refresh-a",
            token_expiry=datetime.utcnow() + timedelta(hours=1),
            scopes=sheets_scope,
            status="connected",
        )
        connection_b = GoogleConnection(
            organization_id=org_b.id,
            user_id=user_b.id,
            access_token_encrypted="old-b",
            refresh_token_encrypted="refresh-b",
            token_expiry=datetime.utcnow() + timedelta(hours=1),
            scopes="org-b-scope",
            status="connected",
        )
        state = GoogleOAuthState(
            state_token="state-org-a",
            organization_id=org_a.id,
            user_id=user_a.id,
            scopes=f"{sheets_scope} {drive_scope}",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            used=False,
        )
        db.add_all([connection_a, connection_b, state])
        db.commit()
        client = client_factory(org_b)
        token_response = MagicMock()
        token_response.raise_for_status = MagicMock()
        token_response.json.return_value = {
            "access_token": "new-access",
            "expires_in": 3600,
            "scope": drive_scope,
        }
        user_response = MagicMock(
            status_code=200
        )
        user_response.json.return_value = {
            "email": "orga@example.com"
        }

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
        }), patch(
            "app.api.google.httpx.post",
            return_value=token_response,
        ), patch(
            "app.api.google.httpx.get",
            return_value=user_response,
        ), patch(
            "app.api.google.encrypt_google_secret",
            side_effect=lambda value: f"encrypted-{value}",
        ):
            response = client.get(
                "/api/integrations/google/oauth/callback",
                params={"code": "code-a", "state": state.state_token},
                follow_redirects=False,
            )

        assert response.status_code == 302
        db.refresh(connection_a)
        db.refresh(connection_b)
        assert connection_a.organization_id == org_a.id
        assert set(connection_a.scopes.split()) == {
            sheets_scope, drive_scope
        }
        assert connection_a.access_token_encrypted == (
            "encrypted-new-access"
        )
        assert connection_b.organization_id == org_b.id
        assert connection_b.access_token_encrypted == "old-b"
        assert connection_b.scopes == "org-b-scope"


# =========================================================
# GOOGLE DRIVE / DOCS PHASE 2
# =========================================================


class TestGoogleDrivePhase2:
    def _connection(self, db, org, user, scopes):
        connection = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            access_token_encrypted="enc-access",
            refresh_token_encrypted="enc-refresh",
            token_expiry=datetime.utcnow() + timedelta(hours=1),
            scopes=scopes,
            status="connected",
        )
        db.add(connection)
        db.commit()
        return connection

    def test_sheets_oauth_stays_minimal(self, client_factory, db):
        org = _make_org(db)
        client = client_factory(org)

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            response = client.get(
                "/api/integrations/google/oauth/start"
            )

        assert response.status_code == 200
        url = response.json()["authorization_url"]
        assert "drive.metadata.readonly" in url
        assert "drive.readonly" not in url

    def test_expand_scopes_requests_drive_readonly(
        self, client_factory, db
    ):
        org = _make_org(db)
        client = client_factory(org)

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            response = client.get(
                "/api/integrations/google/oauth/expand-scopes"
            )

        assert response.status_code == 200
        url = response.json()["authorization_url"]
        assert "drive.readonly" in url

    def test_drive_files_requires_incremental_scope(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        self._connection(
            db,
            org,
            user,
            "https://www.googleapis.com/auth/spreadsheets.readonly "
            "https://www.googleapis.com/auth/drive.metadata.readonly",
        )
        client = client_factory(org)

        response = client.get(
            "/api/integrations/google/drive/files"
        )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == (
            "INSUFFICIENT_SCOPES"
        )

    def test_drive_files_returns_sanitized_metadata(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        self._connection(
            db,
            org,
            user,
            "https://www.googleapis.com/auth/drive.readonly",
        )
        client = client_factory(org)

        with patch(
            "app.api.google._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.google_drive_client.list_drive_files",
            return_value={
                "files": [{
                    "id": "file-1",
                    "name": "Policies.pdf",
                    "mimeType": "application/pdf",
                    "modifiedTime": "2026-08-31T12:00:00Z",
                    "size": "20",
                    "parents": ["folder-1"],
                    "owners": [{"emailAddress": "hidden@test.com"}],
                }],
                "nextPageToken": "next",
            },
        ) as mocked_list:
            response = client.get(
                "/api/integrations/google/drive/files",
                params={"query": "Policies", "page_token": "p1"},
            )

        assert response.status_code == 200
        assert response.json()["files"] == [{
            "id": "file-1",
            "name": "Policies.pdf",
            "mime_type": "application/pdf",
            "modified_time": "2026-08-31T12:00:00Z",
            "size": "20",
            "parents": ["folder-1"],
        }]
        assert response.json()["next_page_token"] == "next"
        assert mocked_list.await_args.kwargs["page_token"] == "p1"

    def test_delete_folder_deactivates_children_once(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        folder = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Knowledge",
            source_type="google_drive_folder",
            s3_bucket="",
            s3_key="",
            external_id="folder-1",
            status="uploaded",
        )
        db.add(folder)
        db.flush()
        child = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Policies.pdf",
            source_type="google_drive_file",
            s3_bucket="bucket",
            s3_key="key",
            parent_source_id=folder.id,
            external_id="file-1",
            status="uploaded",
        )
        db.add(child)
        db.commit()
        client = client_factory(org)

        with patch(
            "app.services.knowledge_source_lifecycle.delete_knowledge_file"
        ) as delete_file, patch(
            "app.services.knowledge_ingestion.start_ingestion_job",
            return_value="job-1",
        ) as start_job:
            response = client.delete(
                f"/api/knowledge-bases/{kb.id}/sources/{folder.id}"
            )

        assert response.status_code == 200
        delete_file.assert_called_once_with("bucket", "key")
        start_job.assert_called_once_with(
            "bedrock-kb-123", "bedrock-ds-456"
        )
        db.refresh(folder)
        db.refresh(child)
        assert folder.active is False
        assert child.active is False

    def test_delete_kb_without_bedrock_ids_is_rejected(
        self, client_factory, db
    ):
        """A source mutation cannot run before remote provisioning is ready."""
        org = _make_org(db)
        user, _ = _make_user(db, org)

        kb_no_bedrock = KnowledgeBase(
            organization_id=org.id,
            name="No Bedrock KB",
            scope="selected_stores",
            external_id=None,
            external_data_source_id=None,
        )
        db.add(kb_no_bedrock)
        db.flush()

        source = KnowledgeSource(
            knowledge_base_id=kb_no_bedrock.id,
            organization_id=org.id,
            name="Test Sheet - Sheet1",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/Sheet1.csv",
            status="active",
            external_id="1AbCdEfGhIjKlMnOpQrStUvWxYz",
            sheet_name="Sheet1",
            sync_status="synced",
        )
        db.add(source)
        db.commit()

        client = client_factory(org)

        with patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.services.knowledge_ingestion.start_ingestion_job"
        ) as mock_ingest:
            resp = client.delete(
                f"/api/knowledge-bases/{kb_no_bedrock.id}/sources/{source.id}",
            )

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == (
            "KNOWLEDGE_BASE_NOT_READY"
        )
        mock_delete.assert_not_called()
        mock_ingest.assert_not_called()
        db.refresh(source)
        assert source.active is True

    def test_delete_ingestion_failure(
        self, client_factory, db
    ):
        """C. StartIngestionJob fails after S3 delete → source still deleted"""
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="Test Sheet - Sheet1",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-123/Sheet1.csv",
            status="active",
            external_id="1AbCdEfGhIjKlMnOpQrStUvWxYz",
            sheet_name="Sheet1",
            sync_status="synced",
        )
        db.add(source)
        db.commit()

        client = client_factory(org)

        with patch(
            "app.services.knowledge_source_lifecycle.delete_knowledge_file"
        ), patch(
            "app.services.knowledge_ingestion.start_ingestion_job",
            return_value=None,
        ):
            resp = client.delete(
                f"/api/knowledge-bases/{kb.id}/sources/{source.id}",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["reindex_status"] == "reindex_failed"
        assert data["ingestion_job_id"] is None

        db.refresh(source)
        assert source.active is False
        assert source.status == "deleted"

    def test_cross_tenant_delete_blocked(
        self, client_factory, db
    ):
        """D. Cross-tenant delete → 404, no S3 delete, no Bedrock"""
        org_a = _make_org(db)
        org_b = _make_org(db)

        user_b, _ = _make_user(db, org_b)
        kb_b = _make_kb(db, org_b)

        source_b = KnowledgeSource(
            knowledge_base_id=kb_b.id,
            organization_id=org_b.id,
            name="Org B Sheet",
            source_type="google_sheet",
            s3_bucket="diaglob-bucket",
            s3_key="google/sheet-b/Sheet1.csv",
            status="active",
            external_id="1AbCdEfGhIjKlMnOpQrStUvWxYz",
            sheet_name="Sheet1",
            sync_status="synced",
        )
        db.add(source_b)
        db.commit()

        client_a = client_factory(org_a)

        with patch(
            "app.services.knowledge_sources.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.services.knowledge_ingestion.start_ingestion_job"
        ) as mock_ingest:
            resp = client_a.delete(
                f"/api/knowledge-bases/{kb_b.id}/sources/{source_b.id}",
            )

        assert resp.status_code == 404
        mock_delete.assert_not_called()
        mock_ingest.assert_not_called()

    def test_file_source_delete_also_reindexes(
        self, client_factory, db
    ):
        """E. Normal file source delete also triggers Bedrock reindex"""
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)

        source = KnowledgeSource(
            knowledge_base_id=kb.id,
            organization_id=org.id,
            name="document.pdf",
            source_type="file",
            s3_bucket="diaglob-bucket",
            s3_key="uploads/doc.pdf",
            status="active",
            sync_status=None,
        )
        db.add(source)
        db.commit()

        client = client_factory(org)

        with patch(
            "app.services.knowledge_source_lifecycle.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.services.knowledge_ingestion.start_ingestion_job",
            return_value="job-file-cleanup",
        ) as mock_ingest:
            resp = client.delete(
                f"/api/knowledge-bases/{kb.id}/sources/{source.id}",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["reindex_status"] == "indexing"
        assert data["ingestion_job_id"] == "job-file-cleanup"
        mock_delete.assert_called_once_with(
            "diaglob-bucket",
            "uploads/doc.pdf",
        )
        mock_ingest.assert_called_once_with(
            "bedrock-kb-123",
            "bedrock-ds-456",
        )


class TestDriveErrorContractRegression:
    """Regression tests for Block 4.1 error contract fix.

    GoogleDriveFileTooLarge inherits from ValueError. After Block 4,
    `except ValueError` was placed before `except (GoogleDriveFileTooLarge, ValueError)`,
    causing GoogleDriveFileTooLarge to be misclassified as DRIVE_SOURCE_CONFLICT (409)
    instead of FILE_TOO_LARGE (400).
    """

    def _connection(self, db, org, user, scopes="https://www.googleapis.com/auth/drive.readonly"):
        conn = GoogleConnection(
            organization_id=org.id,
            user_id=user.id,
            access_token_encrypted="enc-access",
            refresh_token_encrypted="enc-refresh",
            token_expiry=datetime.utcnow() + timedelta(hours=1),
            scopes=scopes,
            status="connected",
        )
        db.add(conn)
        db.commit()
        return conn

    def test_google_doc_too_large_preserves_contract(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(db, org, user)
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.services.drive_file_sources.export_google_doc",
            side_effect=GoogleDriveFileTooLarge("File exceeds 50MB limit"),
        ):
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/google-doc",
                json={
                    "file_id": "doc-1",
                    "file_name": "Large Doc",
                    "mime_type": "application/vnd.google-apps.document",
                },
            )

        assert response.status_code == 400
        data = response.json()
        detail = data.get("detail", data)
        assert detail["code"] == "FILE_TOO_LARGE"
        assert "50MB" in detail["message"]

    def test_drive_file_too_large_preserves_contract(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(db, org, user)
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.services.drive_file_sources.download_drive_file",
            side_effect=GoogleDriveFileTooLarge("File exceeds 50MB limit"),
        ):
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/google-drive-file",
                json={
                    "file_id": "file-1",
                    "file_name": "Large File.pdf",
                    "mime_type": "application/pdf",
                },
            )

        assert response.status_code == 400
        data = response.json()
        detail = data.get("detail", data)
        assert detail["code"] == "FILE_TOO_LARGE"
        assert "50MB" in detail["message"]

    def test_drive_source_conflict_remains_409(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(db, org, user)

        existing = KnowledgeSource(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            name="Existing.pdf",
            source_type="google_drive_file",
            s3_bucket="bucket",
            s3_key="key",
            external_id="file-1",
            status="uploaded",
            sync_status="synced",
        )
        db.add(existing)
        db.commit()

        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ):
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/google-drive-file",
                json={
                    "file_id": "file-1",
                    "file_name": "Existing.pdf",
                    "mime_type": "application/pdf",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source_id"] == existing.id
        assert "already exists" in data["message"]

    def test_provider_valueerror_not_misclassified_as_conflict(
        self, client_factory, db
    ):
        org = _make_org(db)
        user, _ = _make_user(db, org)
        kb = _make_kb(db, org)
        self._connection(db, org, user)
        client = client_factory(org)

        with patch(
            "app.api.knowledge._get_valid_google_token",
            return_value="token",
        ), patch(
            "app.services.drive_file_sources.download_drive_file",
            side_effect=ValueError("Invalid file ID format"),
        ):
            response = client.post(
                f"/api/knowledge-bases/{kb.id}/sources/google-drive-file",
                json={
                    "file_id": "bad-id",
                    "file_name": "Bad File",
                    "mime_type": "application/pdf",
                },
            )

        assert response.status_code != 409
        assert response.status_code != 200
