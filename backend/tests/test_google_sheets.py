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
def setup_db():
    global _user_counter, _org_counter
    _user_counter = 0
    _org_counter = 0
    _rate_limit_store.clear()
    Base.metadata.create_all(bind=engine)
    yield
    _rate_limit_store.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
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
            "app.main.decrypt_google_secret",
            return_value="decrypted-token",
        ):
            with patch(
                "app.main.httpx"
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
            "app.main._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.main.httpx.AsyncClient"
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
            "app.main._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.main.httpx.AsyncClient"
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
            "app.main._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.main.httpx.AsyncClient"
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
                    "app.main.upload_knowledge_file"
                ) as mock_upload:
                    mock_upload.return_value = {
                        "bucket": "diaglob-bucket",
                        "key": "google/sheet-key/Sheet1.csv",
                    }
                    with patch(
                        "app.main.start_ingestion_job",
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


class TestSyncGoogleSheetSource:
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
            "app.main._get_valid_google_token",
            return_value="valid-token",
        ):
            with patch(
                "app.main.httpx.AsyncClient"
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
                    "app.main.upload_knowledge_file"
                ) as mock_upload:
                    mock_upload.return_value = {
                        "bucket": "diaglob-bucket",
                        "key": "google/sheet-key/Sheet1.csv",
                    }
                    with patch(
                        "app.main.start_ingestion_job",
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
            "app.main.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.main.start_ingestion_job",
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

    def test_delete_kb_without_bedrock_ids(
        self, client_factory, db
    ):
        """B. KB without Bedrock IDs → S3 deleted, no ingestion, not_configured"""
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
            "app.main.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.main.start_ingestion_job"
        ) as mock_ingest:
            resp = client.delete(
                f"/api/knowledge-bases/{kb_no_bedrock.id}/sources/{source.id}",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["reindex_status"] == "not_configured"
        assert data["ingestion_job_id"] is None
        mock_delete.assert_called_once()
        mock_ingest.assert_not_called()

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
            "app.main.delete_knowledge_file"
        ), patch(
            "app.main.start_ingestion_job",
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
            "app.main.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.main.start_ingestion_job"
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
            "app.main.delete_knowledge_file"
        ) as mock_delete, patch(
            "app.main.start_ingestion_job",
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
