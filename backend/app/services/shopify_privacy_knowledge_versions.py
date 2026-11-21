"""Delete ALL S3 object versions of one independently permitted KB documents prefix.

A normal DeleteObject on a versioned S3 bucket only creates a delete marker.
This opt-in GDPR helper deletes exact version IDs and delete-marker IDs after
complete read-only enumeration, then independently re-lists the prefix. It
does not infer subject ownership: the caller must enforce tenant, store,
exclusive-KB linkage, legal review, and case-specific execution permits first.

Never call for a shared Knowledge Base or before legal-hold clearance.
"""
from __future__ import annotations

from .. import knowledge_storage

MAX_VERSIONS_PER_KB = 10_000
BATCH_SIZE = 1000


class ShopifyPrivacyS3VersionError(ValueError):
    """Opaque, PII-free failure codes. Never echo keys or bucket names."""


def _fail(code: str):
    raise ShopifyPrivacyS3VersionError(code)


def _kb_prefix(organization_id: int, knowledge_base_id: int) -> str:
    if (type(organization_id) is not int or organization_id <= 0
            or type(knowledge_base_id) is not int or knowledge_base_id <= 0):
        _fail("PRIVACY_S3_KNOWLEDGE_SCOPE_INVALID")
    return (
        f"organizations/{organization_id}/knowledge-bases/"
        f"{knowledge_base_id}/documents/"
    )


def _versions(s3, *, bucket: str, prefix: str) -> tuple[list[dict], int]:
    """Bounded complete scan BEFORE any destructive operation."""
    items: list[dict] = []
    delete_marker_count = 0
    marker_pair: tuple[str | None, str | None] = (None, None)
    seen_pages: set[tuple[str | None, str | None]] = set()
    seen_ids: set[tuple[str, str]] = set()
    while True:
        if marker_pair in seen_pages:
            _fail("PRIVACY_S3_VERSION_PAGINATION_LOOP")
        seen_pages.add(marker_pair)
        params = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": BATCH_SIZE}
        if marker_pair[0] is not None:
            params["KeyMarker"] = marker_pair[0]
        if marker_pair[1] is not None:
            params["VersionIdMarker"] = marker_pair[1]
        try:
            page = s3.list_object_versions(**params)
        except Exception as exc:
            raise ShopifyPrivacyS3VersionError(
                "PRIVACY_S3_VERSION_LIST_FAILED"
            ) from exc
        for kind, source in (
            ("version", page.get("Versions", [])),
            ("delete_marker", page.get("DeleteMarkers", [])),
        ):
            for item in source:
                key, version_id = item.get("Key"), item.get("VersionId")
                if (not isinstance(key, str) or not key.startswith(prefix)
                        or len(key) <= len(prefix)
                        or not isinstance(version_id, str) or not version_id):
                    _fail("PRIVACY_S3_VERSION_SCOPE_DRIFT")
                identity = (key, version_id)
                if identity in seen_ids:
                    _fail("PRIVACY_S3_VERSION_DUPLICATED")
                seen_ids.add(identity)
                items.append({"Key": key, "VersionId": version_id})
                if kind == "delete_marker":
                    delete_marker_count += 1
                if len(items) > MAX_VERSIONS_PER_KB:
                    _fail("PRIVACY_S3_VERSION_SCOPE_LIMIT")
        if not page.get("IsTruncated"):
            break
        next_pair = (page.get("NextKeyMarker"), page.get("NextVersionIdMarker"))
        if not next_pair[0] or next_pair == marker_pair:
            _fail("PRIVACY_S3_VERSION_PAGINATION_INVALID")
        marker_pair = next_pair
    return items, delete_marker_count


def delete_exclusive_shop_knowledge_versions(
    organization_id: int, knowledge_base_id: int,
    *, client=None, bucket: str | None = None,
) -> dict:
    """Explicit GDPR version purge for an approved **exclusive** KB only.

    Fails closed on versioning disabled, scope drift, pagination limits,
    per-object errors, partial S3 response or post-delete re-list. Any failure
    after a provider operation needs manual reconciliation of the original
    signed plan; the outer knowledge-erasure journal records that state.
    """
    prefix = _kb_prefix(organization_id, knowledge_base_id)
    bucket = knowledge_storage.KNOWLEDGE_BUCKET if bucket is None else bucket
    if not isinstance(bucket, str) or not bucket:
        _fail("PRIVACY_S3_KNOWLEDGE_BUCKET_REQUIRED")
    s3 = client or knowledge_storage.get_s3_client()
    try:
        versioning = s3.get_bucket_versioning(Bucket=bucket)
    except Exception as exc:
        raise ShopifyPrivacyS3VersionError(
            "PRIVACY_S3_VERSIONING_UNVERIFIED"
        ) from exc
    if versioning.get("Status") != "Enabled":
        _fail("PRIVACY_S3_VERSIONING_REQUIRED")
    items, delete_markers = _versions(s3, bucket=bucket, prefix=prefix)
    for index in range(0, len(items), BATCH_SIZE):
        batch = items[index:index + BATCH_SIZE]
        try:
            response = s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": batch, "Quiet": False},
            )
        except Exception as exc:
            raise ShopifyPrivacyS3VersionError(
                "PRIVACY_S3_VERSION_PURGE_FAILED"
            ) from exc
        if response.get("Errors"):
            _fail("PRIVACY_S3_VERSION_PURGE_ERRORS")
        acknowledged = {
            (entry.get("Key"), entry.get("VersionId"))
            for entry in response.get("Deleted", [])
        }
        if acknowledged != {
            (entry["Key"], entry["VersionId"]) for entry in batch
        }:
            _fail("PRIVACY_S3_VERSION_DELETE_UNCONFIRMED")
    residual, residual_markers = _versions(s3, bucket=bucket, prefix=prefix)
    if residual or residual_markers:
        _fail("PRIVACY_S3_VERSION_REMAINING_AFTER_PURGE")
    return {
        "versions_deleted": len(items) - delete_markers,
        "delete_markers_deleted": delete_markers,
        "prefix_versions_remaining": 0,
        "provider_erasure_independently_verified": False,
        "fulfillment_complete": False,
    }
