"""
Google Sheets API client for Diaglob Knowledge Bases.

Handles:
- Fetching spreadsheet metadata
- Listing tabs
- Fetching sheet values
- Normalizing to CSV for Bedrock ingestion
"""

import csv
import io
import logging
import os
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

MAX_ROWS = int(
    os.getenv("GOOGLE_SHEETS_MAX_ROWS", "10000")
)
MAX_COLUMNS = int(
    os.getenv("GOOGLE_SHEETS_MAX_COLUMNS", "50")
)
MAX_CELLS = int(
    os.getenv("GOOGLE_SHEETS_MAX_CELLS", "250000")
)


def extract_spreadsheet_id(url_or_id: str) -> str | None:
    """Extract spreadsheet ID from a Google Sheets URL or raw ID.

    Supports:
    - https://docs.google.com/spreadsheets/d/{ID}/edit...
    - https://docs.google.com/spreadsheets/d/{ID}/
    - Raw spreadsheet ID string
    """
    if not url_or_id:
        return None

    text = url_or_id.strip()

    # Try URL parsing
    try:
        parsed = urlparse(text)
        if "google.com" in (parsed.hostname or ""):
            parts = parsed.path.strip("/").split("/")
            if "d" in parts:
                idx = parts.index("d")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
    except Exception:
        pass

    # Try regex for spreadsheet ID pattern
    match = re.search(
        r"/spreadsheets/d/([a-zA-Z0-9_-]+)",
        text,
    )
    if match:
        return match.group(1)

    # Assume raw ID if it looks like one
    if re.match(r"^[a-zA-Z0-9_-]{20,}$", text):
        return text

    return None


def _get_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


async def get_spreadsheet_metadata(
    access_token: str,
    spreadsheet_id: str,
) -> dict:
    """Fetch spreadsheet metadata including sheet/tab names.

    Returns:
        {
            "title": str,
            "sheets": [{"sheetId": int, "title": str, "index": int}]
        }

    Raises:
        httpx.HTTPStatusError on API errors.
    """
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}"
    params = {"fields": "properties.title,sheets.properties"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url,
            headers=_get_headers(access_token),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    title = data.get("properties", {}).get("title", "Untitled")
    sheets = []
    for sheet in data.get("sheets", []):
        props = sheet.get("properties", {})
        sheets.append({
            "sheetId": props.get("sheetId"),
            "title": props.get("title", ""),
            "index": props.get("index", 0),
        })

    return {"title": title, "sheets": sheets}


async def fetch_sheet_values(
    access_token: str,
    spreadsheet_id: str,
    sheet_name: str,
) -> list[list[str]]:
    """Fetch all values from a specific sheet/tab.

    Uses FORMATTED_VALUE to get human-readable content.
    Returns list of rows, each row is a list of cell strings.

    Raises:
        ValueError if limits exceeded.
        httpx.HTTPStatusError on API errors.
    """
    range_name = f"'{sheet_name}'" if sheet_name else ""

    url = (
        f"{SHEETS_API_BASE}/{spreadsheet_id}"
        f"/values/{range_name}"
    )
    params = {
        "valueRenderOption": "FORMATTED_VALUE",
        "majorDimension": "ROWS",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            url,
            headers=_get_headers(access_token),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    values = data.get("values", [])

    if not values:
        return []

    # Apply limits
    row_count = len(values)
    if row_count > MAX_ROWS:
        raise ValueError(
            f"Sheet has {row_count} rows, "
            f"exceeds limit of {MAX_ROWS}"
        )

    col_count = max(len(row) for row in values)
    if col_count > MAX_COLUMNS:
        raise ValueError(
            f"Sheet has {col_count} columns, "
            f"exceeds limit of {MAX_COLUMNS}"
        )

    total_cells = row_count * col_count
    if total_cells > MAX_CELLS:
        raise ValueError(
            f"Sheet has {total_cells} cells, "
            f"exceeds limit of {MAX_CELLS}"
        )

    return values


def normalize_to_csv(
    values: list[list[str]],
    spreadsheet_title: str = "",
    sheet_name: str = "",
) -> str:
    """Normalize sheet values to a well-formed CSV string.

    - Uses csv.writer for proper escaping
    - UTF-8 output
    - Detects headers from first row
    - Skips completely empty rows
    - Pads rows to uniform column count
    """
    if not values:
        return ""

    # Filter out completely empty rows
    non_empty = [
        row for row in values
        if any(cell.strip() for cell in row)
    ]

    if not non_empty:
        return ""

    # Pad all rows to same column count
    max_cols = max(len(row) for row in non_empty)
    padded = []
    for row in non_empty:
        padded.append(
            row + [""] * (max_cols - len(row))
        )

    # Generate column headers if first row looks like data
    headers = padded[0]
    has_headers = all(
        h.strip() for h in headers if h.strip()
    )
    if not has_headers:
        headers = [
            f"column_{i + 1}"
            for i in range(max_cols)
        ]
        padded.insert(0, headers)

    # Write CSV
    output = io.StringIO()
    writer = csv.writer(
        output,
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )

    for row in padded:
        writer.writerow(row)

    return output.getvalue()
