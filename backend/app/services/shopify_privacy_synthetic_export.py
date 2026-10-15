"""Encrypted synthetic customer access export prototype.

No database queries, live receipts, cloud storage, or external delivery.
Production export remains prohibited until field provenance, legal retention,
external processors, and delivery authorization have been reviewed.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

_ALLOWED_SOURCES = frozenset({
    "customer_store_profiles", "orders", "conversations",
    "conversational_checkouts",
})
_ALLOWED_FIELDS = frozenset({"source", "record", "fields"})
_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
_MAX_CIPHERTEXT_BYTES = 1024 * 1024


class SyntheticPrivacyExportError(ValueError):
    """Fail-closed export validation error; never embed input data."""


@dataclass(frozen=True)
class EncryptedSyntheticExport:
    ciphertext: bytes
    sha256: str
    record_count: int
    request_id: str = ""
    synthetic_only: bool = True
    delivery_authorized: bool = False
    fulfillment_complete: bool = False


def build_encrypted_synthetic_export(
    *, manifest: dict, records: list[dict], encryption_key: bytes,
) -> EncryptedSyntheticExport:
    """Create an in-memory encrypted fixture; never permit actual customer data.

    Every row requires an explicit synthetic marker. Counts must match the
    signed-and-scoped *preview manifest*; any unsupported surface is rejected.
    The result is opaque encrypted bytes, never a plaintext downloadable file.
    """
    if not isinstance(manifest, dict) or (
        manifest.get("topic") != "customers/data_request"
        or manifest.get("scope_status") != "scope_preview_only"
        or manifest.get("export_generated") is not False
        or manifest.get("delivery_authorized") is not False
        or manifest.get("fulfillment_complete") is not False
    ):
        raise SyntheticPrivacyExportError("INVALID_EXPORT_MANIFEST")
    request_id = manifest.get("request_id")
    if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
        raise SyntheticPrivacyExportError("UNBOUND_EXPORT_MANIFEST")
    if not isinstance(records, list) or len(records) > 1000:
        raise SyntheticPrivacyExportError("INVALID_SYNTHETIC_RECORDS")
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise SyntheticPrivacyExportError("INVALID_EXPORT_MANIFEST")
    expected = {}
    for item in sources:
        if not isinstance(item, dict):
            raise SyntheticPrivacyExportError("INVALID_EXPORT_MANIFEST")
        name, count = item.get("name"), item.get("matching_records")
        if (type(name) is not str or name not in _ALLOWED_SOURCES or name in expected
                or type(count) is not int or not 0 <= count <= 1000
                or item.get("status") != "review_required"):
            raise SyntheticPrivacyExportError("INVALID_EXPORT_MANIFEST")
        expected[name] = count
    if set(expected) != _ALLOWED_SOURCES:
        raise SyntheticPrivacyExportError("INCOMPLETE_EXPORT_MANIFEST")

    actual = {name: 0 for name in expected}
    sanitized = []
    for row in records:
        if not isinstance(row, dict) or set(row) != _ALLOWED_FIELDS:
            raise SyntheticPrivacyExportError("INVALID_SYNTHETIC_RECORDS")
        source = row.get("source")
        fields = row.get("fields")
        if (type(source) is not str or source not in expected or row.get("record") != "SYNTHETIC"
                or not isinstance(fields, dict) or not fields
                or any(not isinstance(k, str) or not k for k in fields)
                or any(not isinstance(v, (str, int, float, bool, type(None)))
                       for v in fields.values())):
            raise SyntheticPrivacyExportError("NON_SYNTHETIC_EXPORT_BLOCKED")
        # The fixture author must mark every value explicitly as synthetic,
        # so accidental database-derived values cannot pass this interface.
        if any(not isinstance(v, str) or not v.startswith("SYNTHETIC_")
               for v in fields.values()):
            raise SyntheticPrivacyExportError("NON_SYNTHETIC_EXPORT_BLOCKED")
        actual[source] += 1
        sanitized.append(row)
    if actual != expected:
        raise SyntheticPrivacyExportError("EXPORT_COUNT_MISMATCH")
    try:
        cipher = Fernet(encryption_key)
    except (ValueError, TypeError) as exc:
        raise SyntheticPrivacyExportError("INVALID_EXPORT_ENCRYPTION_KEY") from exc
    raw = json.dumps(
        {"schema_version": 1, "synthetic_only": True,
         "request_id": request_id, "records": sanitized},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = cipher.encrypt(raw)
    if len(ciphertext) > _MAX_CIPHERTEXT_BYTES:
        raise SyntheticPrivacyExportError("SYNTHETIC_EXPORT_SIZE_LIMIT")
    return EncryptedSyntheticExport(
        ciphertext=ciphertext,
        sha256=hashlib.sha256(ciphertext).hexdigest(),
        record_count=len(sanitized), request_id=request_id,
    )


def verify_encrypted_synthetic_export(
    *, artifact: EncryptedSyntheticExport, encryption_key: bytes,
    expected_request_id: str,
) -> None:
    """Verify *decrypted* case binding and every synthetic value before issue.

    This validates a fixture contract, not a data-subject identity or a live
    Shopify data export. The issuing service must authenticate the recipient
    and independently check the signed receipt and store/tenant relationship.
    """
    if (
        type(artifact) is not EncryptedSyntheticExport
        or artifact.synthetic_only is not True
        or artifact.delivery_authorized is not False
        or artifact.fulfillment_complete is not False
        or not isinstance(expected_request_id, str)
        or _REQUEST_ID.fullmatch(expected_request_id) is None
        or artifact.request_id != expected_request_id
        or not isinstance(artifact.ciphertext, bytes)
        or not 1 <= len(artifact.ciphertext) <= _MAX_CIPHERTEXT_BYTES
        or type(artifact.record_count) is not int
        or not 0 <= artifact.record_count <= 1000
        or not isinstance(artifact.sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)
        or not hashlib.sha256(artifact.ciphertext).hexdigest() == artifact.sha256
    ):
        raise SyntheticPrivacyExportError("UNTRUSTED_SYNTHETIC_ARTIFACT")
    try:
        raw = Fernet(encryption_key).decrypt(artifact.ciphertext)
        document = json.loads(raw)
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise SyntheticPrivacyExportError("UNTRUSTED_SYNTHETIC_ARTIFACT") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "synthetic_only", "request_id", "records"}
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["synthetic_only"] is not True
        or document["request_id"] != expected_request_id
        or not isinstance(document["records"], list)
        or len(document["records"]) != artifact.record_count
    ):
        raise SyntheticPrivacyExportError("UNTRUSTED_SYNTHETIC_ARTIFACT")
    for row in document["records"]:
        if (
            not isinstance(row, dict)
            or set(row) != _ALLOWED_FIELDS
            or type(row["source"]) is not str
            or row["source"] not in _ALLOWED_SOURCES
            or row["record"] != "SYNTHETIC"
            or not isinstance(row["fields"], dict)
            or not row["fields"]
            or any(
                not isinstance(name, str) or not name
                or not isinstance(value, str) or not value.startswith("SYNTHETIC_")
                for name, value in row["fields"].items()
            )
        ):
            raise SyntheticPrivacyExportError("UNTRUSTED_SYNTHETIC_ARTIFACT")
