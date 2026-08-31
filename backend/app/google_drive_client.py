"""
Google Drive API client for Diaglob Knowledge Bases.

Handles:
- Listing Drive files with MIME type filters
- Downloading file content
- Exporting Google Docs to plain text
- Listing folders
- Pagination support
- File size limits
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

DEFAULT_MAX_FILE_SIZE_MB = 25
DEFAULT_MAX_FILES_PER_FOLDER = 100
DEFAULT_MAX_TOTAL_SYNC_MB = 100


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


MAX_FILE_SIZE_MB = _positive_int_env(
    "GOOGLE_DRIVE_MAX_FILE_SIZE_MB",
    DEFAULT_MAX_FILE_SIZE_MB,
)
MAX_FILES_PER_FOLDER = _positive_int_env(
    "GOOGLE_DRIVE_MAX_FILES_PER_FOLDER",
    DEFAULT_MAX_FILES_PER_FOLDER,
)
MAX_TOTAL_SYNC_MB = _positive_int_env(
    "GOOGLE_DRIVE_MAX_TOTAL_SYNC_MB",
    DEFAULT_MAX_TOTAL_SYNC_MB,
)
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_TOTAL_SYNC_BYTES = MAX_TOTAL_SYNC_MB * 1024 * 1024

SUPPORTED_MIME_TYPES = {
    "application/pdf": True,
    "text/plain": True,
    "text/csv": True,
    (
        "application/vnd.openxmlformats-officedocument"
        ".spreadsheetml.sheet"
    ): True,
    (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ): True,
    (
        "application/vnd.google-apps.document"
    ): True,
}

SUPPORTED_MIME_QUERY = " or ".join(
    f"mimeType='{mt}'" for mt in SUPPORTED_MIME_TYPES
)

FOLDER_MIME_TYPE = (
    "application/vnd.google-apps.folder"
)

DRIVE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


class GoogleDriveFileTooLarge(ValueError):
    """Raised when downloaded Drive content exceeds the size limit."""


def _escape_query_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _validate_drive_id(drive_id: str) -> None:
    if (
        not isinstance(drive_id, str)
        or not DRIVE_ID_PATTERN.fullmatch(drive_id)
    ):
        raise ValueError("Invalid Google Drive file or folder ID")


async def _read_limited_response(
    response: httpx.Response,
    max_bytes: int,
) -> bytes:
    content = bytearray()
    total_bytes = 0
    async for chunk in response.aiter_bytes():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise GoogleDriveFileTooLarge(
                f"File content exceeds limit of {max_bytes} bytes"
            )
        content.extend(chunk)
    return bytes(content)


def _get_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def is_supported_mime_type(mime_type: str) -> bool:
    return mime_type in SUPPORTED_MIME_TYPES


def is_google_doc(mime_type: str) -> bool:
    return (
        mime_type
        == "application/vnd.google-apps.document"
    )


async def list_drive_files(
    access_token: str,
    search: str = "",
    folder_id: str | None = None,
    mime_types: set[str] | None = None,
    page_size: int = 50,
    page_token: str | None = None,
    fields: str = (
        "nextPageToken,"
        "files(id,name,mimeType,modifiedTime,size,"
        "parents)"
    ),
) -> dict:
    """List files from Google Drive with pagination.

    Args:
        access_token: Valid Google access token.
        search: Text search in the file name.
        folder_id: Restrict results to direct folder children.
        mime_types: Optional supported MIME type subset.
        page_size: Results per page (max 100).
        page_token: Token for next page.
        fields: Fields to return.

    Returns:
        {
            "files": [{"id", "name", "mimeType",
                        "modifiedTime", "size", "parents"}],
            "nextPageToken": str | None
        }
    """
    q_parts = ["trashed=false"]
    if search:
        escaped_search = _escape_query_literal(search)
        q_parts.append(
            f"name contains '{escaped_search}'"
        )
    if folder_id is not None:
        _validate_drive_id(folder_id)
        q_parts.append(f"'{folder_id}' in parents")

    allowed_mimes = mime_types or set(SUPPORTED_MIME_TYPES)
    unsupported_mimes = allowed_mimes - SUPPORTED_MIME_TYPES.keys()
    if unsupported_mimes:
        unsupported = ", ".join(sorted(unsupported_mimes))
        raise ValueError(f"Unsupported MIME type filter: {unsupported}")
    mime_query = " or ".join(
        f"mimeType='{mime}'"
        for mime in sorted(allowed_mimes)
    )
    q_parts.append(f"({mime_query})")

    full_query = " and ".join(q_parts)

    params: dict = {
        "q": full_query,
        "fields": fields,
        "pageSize": min(page_size, 100),
        "orderBy": "modifiedTime desc",
    }

    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{DRIVE_API_BASE}/files",
            headers=_get_headers(access_token),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    files = data.get("files", [])
    return {
        "files": files,
        "nextPageToken": data.get("nextPageToken"),
    }


async def list_drive_folders(
    access_token: str,
    search: str = "",
    page_size: int = 50,
    page_token: str | None = None,
) -> dict:
    """List folders from Google Drive with pagination.

    Returns:
        {
            "folders": [{"id", "name", "modifiedTime"}],
            "nextPageToken": str | None
        }
    """
    q_parts = [
        "trashed=false",
        f"mimeType='{FOLDER_MIME_TYPE}'",
    ]
    if search:
        escaped_search = _escape_query_literal(search)
        q_parts.append(
            f"name contains '{escaped_search}'"
        )

    full_query = " and ".join(q_parts)

    params: dict = {
        "q": full_query,
        "fields": (
            "nextPageToken,"
            "files(id,name,modifiedTime)"
        ),
        "pageSize": min(page_size, 100),
        "orderBy": "name",
    }

    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{DRIVE_API_BASE}/files",
            headers=_get_headers(access_token),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    folders = data.get("files", [])
    return {
        "folders": folders,
        "nextPageToken": data.get("nextPageToken"),
    }


async def list_folder_children(
    access_token: str,
    folder_id: str,
    page_size: int = 100,
    page_token: str | None = None,
) -> dict:
    """List all supported files in a specific folder.

    Only returns files matching SUPPORTED_MIME_TYPES.
    Does NOT recurse into sub-folders (Phase 1).

    Returns:
        {
            "files": [{"id", "name", "mimeType",
                        "modifiedTime", "size"}],
            "nextPageToken": str | None,
            "total_count": int,
            "limit_exceeded": bool
        }
    """
    _validate_drive_id(folder_id)
    q_parts = [
        "trashed=false",
        f"'{folder_id}' in parents",
        f"({SUPPORTED_MIME_QUERY})",
    ]

    full_query = " and ".join(q_parts)

    all_files = []
    token = page_token
    seen_tokens = {page_token} if page_token else set()

    while True:
        params: dict = {
            "q": full_query,
            "fields": (
                "nextPageToken,"
                "files(id,name,mimeType,"
                "modifiedTime,size)"
            ),
            "pageSize": min(page_size, 100),
        }

        if token:
            params["pageToken"] = token

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{DRIVE_API_BASE}/files",
                headers=_get_headers(access_token),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        batch = data.get("files", [])
        all_files.extend(batch)
        next_token = data.get("nextPageToken")

        if next_token and next_token in seen_tokens:
            raise RuntimeError(
                "Google Drive pagination returned a repeated page token"
            )
        if next_token:
            seen_tokens.add(next_token)
        token = next_token

        if not token or len(all_files) >= MAX_FILES_PER_FOLDER:
            break

    return {
        "files": all_files[:MAX_FILES_PER_FOLDER],
        "nextPageToken": token,
        "total_count": len(
            all_files[:MAX_FILES_PER_FOLDER]
        ),
        "limit_exceeded": bool(token),
    }


async def get_file_metadata(
    access_token: str,
    file_id: str,
) -> dict:
    """Get metadata for a single Drive file.

    Returns:
        {"id", "name", "mimeType", "modifiedTime",
         "size", "parents"}
    """
    _validate_drive_id(file_id)
    params = {
        "fields": (
            "id,name,mimeType,modifiedTime,size,parents"
        ),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{DRIVE_API_BASE}/files/{file_id}",
            headers=_get_headers(access_token),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()


async def download_drive_file(
    access_token: str,
    file_id: str,
) -> bytes:
    """Download file content from Google Drive.

    For native Google files (Docs, Sheets, etc.),
    use export instead.

    Returns:
        Raw file content as bytes.

    Raises:
        GoogleDriveFileTooLarge if file is too large.
        httpx.HTTPStatusError on API errors.
    """
    _validate_drive_id(file_id)
    metadata = await get_file_metadata(
        access_token, file_id
    )

    file_size = int(metadata.get("size", 0))

    if file_size > MAX_FILE_SIZE_BYTES:
        raise GoogleDriveFileTooLarge(
            f"File size {file_size} bytes exceeds "
            f"limit of {MAX_FILE_SIZE_BYTES} bytes "
            f"({MAX_FILE_SIZE_MB}MB)"
        )

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "GET",
            (
                f"{DRIVE_API_BASE}/files/{file_id}"
                f"?alt=media"
            ),
            headers=_get_headers(access_token),
        ) as resp:
            resp.raise_for_status()
            return await _read_limited_response(
                resp, MAX_FILE_SIZE_BYTES
            )


async def export_google_doc(
    access_token: str,
    file_id: str,
    export_mime_type: str = "text/plain",
) -> bytes:
    """Export a Google Doc to a specified MIME type.

    Uses Drive API files.export for native Google
    document types.

    Args:
        access_token: Valid Google access token.
        file_id: Google Drive file ID.
        export_mime_type: Target format. Default
            text/plain.

    Returns:
        Exported content as bytes.

    Raises:
        GoogleDriveFileTooLarge if exported content is too large.
        httpx.HTTPStatusError on API errors.
    """
    _validate_drive_id(file_id)
    params = {
        "mimeType": export_mime_type,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "GET",
            (
                f"{DRIVE_API_BASE}/files/{file_id}"
                f"/export"
            ),
            headers=_get_headers(access_token),
            params=params,
        ) as resp:
            resp.raise_for_status()
            return await _read_limited_response(
                resp, MAX_FILE_SIZE_BYTES
            )


def get_supported_extensions() -> dict[str, str]:
    """Return mapping of file extensions to MIME types.

    Returns:
        {".pdf": "application/pdf", ...}
    """
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".xlsx": (
            "application/vnd.openxmlformats"
            "-officedocument.spreadsheetml.sheet"
        ),
        ".docx": (
            "application/vnd.openxmlformats"
            "-officedocument"
            ".wordprocessingml.document"
        ),
    }


def detect_mime_type_from_filename(
    filename: str,
) -> str | None:
    """Detect MIME type from filename extension.

    Returns:
        MIME type string or None if unsupported.
    """
    lower = filename.lower()
    ext_map = get_supported_extensions()

    for ext, mime in ext_map.items():
        if lower.endswith(ext):
            return mime

    return None


def validate_folder_sync_limits(
    files: list[dict],
) -> str | None:
    """Validate folder sync file list against limits.

    Args:
        files: List of file metadata dicts.

    Returns:
        None if OK, error message string if invalid.
    """
    if len(files) > MAX_FILES_PER_FOLDER:
        return (
            f"Folder has {len(files)} files, "
            f"exceeds limit of {MAX_FILES_PER_FOLDER}"
        )

    total_bytes = 0

    for f in files:
        size = int(f.get("size", 0))

        if size > MAX_FILE_SIZE_BYTES:
            return (
                f"File '{f.get('name', 'unknown')}' "
                f"size {size} bytes exceeds "
                f"limit of {MAX_FILE_SIZE_BYTES} bytes "
                f"({MAX_FILE_SIZE_MB}MB)"
            )

        total_bytes += size

        if total_bytes > MAX_TOTAL_SYNC_BYTES:
            return (
                f"Total sync size {total_bytes} bytes "
                f"exceeds limit of {MAX_TOTAL_SYNC_BYTES} bytes "
                f"({MAX_TOTAL_SYNC_MB}MB)"
            )

    return None
