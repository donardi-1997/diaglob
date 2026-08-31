"""Focused tests for the Google Drive Knowledge Source client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.google_drive_client import (
    MAX_FILES_PER_FOLDER,
    download_drive_file,
    export_google_doc,
    is_google_doc,
    is_supported_mime_type,
    list_drive_files,
    list_drive_folders,
    list_folder_children,
    validate_folder_sync_limits,
)


def _async_client(response):
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _response(payload=None, content=b""):
    response = MagicMock()
    response.json.return_value = payload or {}
    response.content = content
    response.raise_for_status = MagicMock()
    return response


class TestGoogleDriveClient:
    def test_supported_mime_types(self):
        assert is_supported_mime_type("application/pdf")
        assert is_supported_mime_type(
            "application/vnd.google-apps.document"
        )
        assert not is_supported_mime_type("image/png")
        assert is_google_doc(
            "application/vnd.google-apps.document"
        )

    def test_list_files_supports_search_and_pagination(self):
        response = _response({
            "files": [{"id": "f1", "name": "FAQ.pdf"}],
            "nextPageToken": "page-2",
        })
        client = _async_client(response)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            result = asyncio.run(list_drive_files(
                "token", search="FAQ", page_token="page-1"
            ))

        assert result["nextPageToken"] == "page-2"
        params = client.get.await_args.kwargs["params"]
        assert "name contains 'FAQ'" in params["q"]
        assert params["pageToken"] == "page-1"

    def test_list_folders_supports_search(self):
        response = _response({"files": []})
        client = _async_client(response)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            result = asyncio.run(list_drive_folders(
                "token", search="knowledge"
            ))

        assert result["folders"] == []
        assert "name contains 'knowledge'" in (
            client.get.await_args.kwargs["params"]["q"]
        )

    def test_folder_children_follow_pages(self):
        first = _response({
            "files": [{"id": "f1"}],
            "nextPageToken": "next",
        })
        second = _response({"files": [{"id": "f2"}]})
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[first, second])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            result = asyncio.run(list_folder_children("token", "folder"))

        assert [f["id"] for f in result["files"]] == ["f1", "f2"]
        assert result["limit_exceeded"] is False

    def test_folder_child_limit_is_reported(self):
        response = _response({
            "files": [{"id": str(i)} for i in range(MAX_FILES_PER_FOLDER)],
            "nextPageToken": "more",
        })
        client = _async_client(response)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            result = asyncio.run(list_folder_children("token", "folder"))

        assert result["limit_exceeded"] is True

    def test_download_rejects_file_over_limit(self):
        metadata = _response({"size": str(26 * 1024 * 1024)})
        client = _async_client(metadata)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            with pytest.raises(ValueError, match="exceeds"):
                asyncio.run(download_drive_file("token", "file"))

    def test_export_google_doc_returns_bytes(self):
        response = _response(content=b"Plain text knowledge")
        client = _async_client(response)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            content = asyncio.run(export_google_doc("token", "doc"))

        assert content == b"Plain text knowledge"
        assert client.get.await_args.kwargs["params"] == {
            "mimeType": "text/plain"
        }

    def test_folder_limits_detect_total_size(self):
        error = validate_folder_sync_limits([
            {"name": "a.pdf", "size": str(101 * 1024 * 1024)},
        ])
        assert error is not None
        assert "exceeds" in error
