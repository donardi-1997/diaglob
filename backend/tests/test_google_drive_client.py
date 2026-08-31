"""Focused tests for the Google Drive Knowledge Source client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.google_drive_client import (
    MAX_FILES_PER_FOLDER,
    GoogleDriveFileTooLarge,
    _positive_int_env,
    download_drive_file,
    export_google_doc,
    is_google_doc,
    is_supported_mime_type,
    list_drive_files,
    list_drive_folders,
    list_folder_children,
    validate_folder_sync_limits,
)


def _async_context(value):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=value)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


def _async_client(response=None, stream_response=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    if stream_response is not None:
        client.stream = MagicMock(
            return_value=_async_context(stream_response)
        )
    return client


def _response(payload=None, content=b"", chunks=None):
    response = MagicMock()
    response.json.return_value = payload or {}
    response.raise_for_status = MagicMock()

    stream_chunks = [content] if chunks is None else chunks

    async def iter_bytes():
        for chunk in stream_chunks:
            yield chunk

    response.aiter_bytes = iter_bytes
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

    @pytest.mark.parametrize(
        ("search", "escaped"),
        [
            ("O'Reilly", r"O\'Reilly"),
            (r"path\file", r"path\\file"),
            (r"owner\'s", r"owner\\\'s"),
        ],
    )
    def test_list_files_escapes_query_literals(self, search, escaped):
        client = _async_client(_response({"files": []}))
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            asyncio.run(list_drive_files("token", search=search))

        query = client.get.await_args.kwargs["params"]["q"]
        assert f"name contains '{escaped}'" in query

    def test_list_files_rejects_invalid_folder_id(self):
        with pytest.raises(ValueError, match="Invalid Google Drive"):
            asyncio.run(list_drive_files(
                "token", folder_id="folder/unsafe"
            ))

    def test_list_files_rejects_unsupported_mime_filter(self):
        with pytest.raises(ValueError, match="image/png"):
            asyncio.run(list_drive_files(
                "token", mime_types={"application/pdf", "image/png"}
            ))

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

    def test_folder_children_reject_repeated_page_token(self):
        first = _response({
            "files": [{"id": "f1"}],
            "nextPageToken": "same-token",
        })
        second = _response({
            "files": [{"id": "f2"}],
            "nextPageToken": "same-token",
        })
        client = _async_client()
        client.get = AsyncMock(side_effect=[first, second])
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            with pytest.raises(RuntimeError, match="repeated page token"):
                asyncio.run(list_folder_children("token", "folder"))

        assert client.get.await_count == 2

    def test_folder_children_propagates_page_two_failure(self):
        first = _response({
            "files": [{"id": "f1"}],
            "nextPageToken": "page-2",
        })
        provider_error = RuntimeError("provider page failed")
        client = _async_client()
        client.get = AsyncMock(side_effect=[first, provider_error])
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            with pytest.raises(RuntimeError) as exc_info:
                asyncio.run(list_folder_children("token", "folder"))

        assert exc_info.value is provider_error

    def test_download_rejects_file_over_limit(self):
        metadata = _response({"size": str(26 * 1024 * 1024)})
        client = _async_client(metadata)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            with pytest.raises(
                GoogleDriveFileTooLarge, match="exceeds"
            ):
                asyncio.run(download_drive_file("token", "file"))

    def test_download_rejects_stream_over_limit_without_size_metadata(self):
        metadata = _response({"id": "file"})
        stream_response = _response(chunks=[b"123", b"456"])
        client = _async_client(metadata, stream_response)
        with (
            patch(
                "app.google_drive_client.httpx.AsyncClient",
                return_value=client,
            ),
            patch(
                "app.google_drive_client.MAX_FILE_SIZE_BYTES", 5
            ),
        ):
            with pytest.raises(GoogleDriveFileTooLarge, match="5 bytes"):
                asyncio.run(download_drive_file("token", "file"))

        assert client.stream.call_count == 1

    def test_export_google_doc_returns_bytes(self):
        response = _response(content=b"Plain text knowledge")
        client = _async_client(stream_response=response)
        with patch(
            "app.google_drive_client.httpx.AsyncClient",
            return_value=client,
        ):
            content = asyncio.run(export_google_doc("token", "doc"))

        assert content == b"Plain text knowledge"
        assert client.stream.call_args.kwargs["params"] == {
            "mimeType": "text/plain"
        }

    def test_export_google_doc_rejects_stream_over_limit(self):
        response = _response(chunks=[b"1234", b"56"])
        client = _async_client(stream_response=response)
        with (
            patch(
                "app.google_drive_client.httpx.AsyncClient",
                return_value=client,
            ),
            patch(
                "app.google_drive_client.MAX_FILE_SIZE_BYTES", 5
            ),
        ):
            with pytest.raises(GoogleDriveFileTooLarge, match="5 bytes"):
                asyncio.run(export_google_doc("token", "doc"))

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("7", 7),
            ("0", 25),
            ("-1", 25),
            ("invalid", 25),
            ("", 25),
        ],
    )
    def test_positive_int_env_uses_safe_defaults(
        self, monkeypatch, value, expected
    ):
        monkeypatch.setenv("TEST_GOOGLE_DRIVE_LIMIT", value)
        assert _positive_int_env(
            "TEST_GOOGLE_DRIVE_LIMIT", 25
        ) == expected

    def test_folder_limits_detect_total_size(self):
        error = validate_folder_sync_limits([
            {"name": "a.pdf", "size": str(101 * 1024 * 1024)},
        ])
        assert error is not None
        assert "exceeds" in error
