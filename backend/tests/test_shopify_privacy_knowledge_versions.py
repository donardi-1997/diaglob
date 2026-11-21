"""No AWS/network: GDPR S3 purge handles historical versions and delete markers."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.services import shopify_privacy_knowledge_versions as m


BASE = "organizations/1/knowledge-bases/10/documents/"


class FakeVersionedS3:
    def __init__(self, *, page_size=2, versioning="Enabled"):
        self.rows = []
        self.page_size = page_size
        self.versioning = versioning
        self.deletes = []
        self.inject_delete_errors = False
        self.omit_ack = False
        self.race_reinsertion = False

    def add(self, key, version, *, marker=False):
        self.rows.append({
            "Key": key, "VersionId": version,
            "marker": marker,
        })

    def get_bucket_versioning(self, *, Bucket):
        return {"Status": self.versioning}

    def list_object_versions(self, *, Bucket, Prefix, MaxKeys,
                             KeyMarker=None, VersionIdMarker=None):
        rows = sorted(
            [r for r in self.rows if r["Key"].startswith(Prefix)],
            key=lambda row: (row["Key"], row["VersionId"]),
        )
        if KeyMarker is not None:
            try:
                i = next(i for i, row in enumerate(rows)
                         if (row["Key"], row["VersionId"]) ==
                         (KeyMarker, VersionIdMarker))
                rows = rows[i + 1:]
            except StopIteration:
                raise AssertionError("bad pagination marker")
        selected = rows[:self.page_size]
        truncated = len(rows) > len(selected)
        previous = selected[-1] if selected else None
        return {
            "Versions": [
                {"Key": r["Key"], "VersionId": r["VersionId"]}
                for r in selected if not r["marker"]
            ],
            "DeleteMarkers": [
                {"Key": r["Key"], "VersionId": r["VersionId"]}
                for r in selected if r["marker"]
            ],
            "IsTruncated": truncated,
            "NextKeyMarker": previous["Key"] if truncated and previous else None,
            "NextVersionIdMarker": previous["VersionId"] if truncated and previous else None,
        }

    def delete_objects(self, *, Bucket, Delete):
        selected = Delete["Objects"]
        assert Delete["Quiet"] is False
        assert len(selected) <= 1000
        self.deletes.extend(deepcopy(selected))
        if self.inject_delete_errors:
            return {"Errors": [{"Code": "AccessDenied"}]}
        for item in selected:
            key, version = item["Key"], item["VersionId"]
            self.rows = [
                row for row in self.rows
                if not (row["Key"] == key and row["VersionId"] == version)
            ]
        if self.race_reinsertion:
            self.add(BASE + "raced.txt", "raced")
        return {
            "Deleted": selected[:-1] if self.omit_ack else selected,
        }


def purge(s3, **opts):
    return m.delete_exclusive_shop_knowledge_versions(
        1, 10, client=s3, bucket="isolated-synthetic-versioned-bucket", **opts,
    )


def test_all_historical_versions_and_delete_markers_removed_only_from_approved_prefix():
    s3 = FakeVersionedS3(page_size=2)
    for key, version, marker in (
        (BASE + "doc.txt", "v1", False),
        (BASE + "doc.txt", "v2", False),
        (BASE + "doc.txt", "v3", True),
        (BASE + "other.pdf", "v1", False),
        ("organizations/1/knowledge-bases/101/documents/private.txt", "keep", False),
        ("organizations/2/knowledge-bases/10/documents/foreign.txt", "keep", False),
    ):
        s3.add(key, version, marker=marker)
    result = purge(s3)
    assert result["versions_deleted"] == 3
    assert result["delete_markers_deleted"] == 1
    assert result["prefix_versions_remaining"] == 0
    assert result["fulfillment_complete"] is False
    assert result["provider_erasure_independently_verified"] is False
    assert {(r["Key"], r["VersionId"]) for r in s3.rows} == {
        ("organizations/1/knowledge-bases/101/documents/private.txt", "keep"),
        ("organizations/2/knowledge-bases/10/documents/foreign.txt", "keep"),
    }
    assert len(s3.deletes) == 4


def test_empty_prefix_remains_empty_without_any_deletes():
    s3 = FakeVersionedS3()
    result = purge(s3)
    assert result["versions_deleted"] == 0
    assert result["prefix_versions_remaining"] == 0
    assert s3.deletes == []


@pytest.mark.parametrize("versioning", ["Suspended", None, "Disabled"])
def test_versioning_must_be_enabled(versioning):
    s3 = FakeVersionedS3(versioning=versioning)
    s3.add(BASE + "private.txt", "old")
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="VERSIONING_REQUIRED"):
        purge(s3)
    assert s3.deletes == []


def test_scope_overflow_is_rejected_before_any_delete(monkeypatch):
    s3 = FakeVersionedS3(page_size=2)
    for n in range(3):
        s3.add(BASE + f"doc-{n}.txt", f"v{n}")
    monkeypatch.setattr(m, "MAX_VERSIONS_PER_KB", 2)
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="SCOPE_LIMIT"):
        purge(s3)
    assert s3.deletes == []


def test_per_object_provider_failure_does_not_claim_success():
    s3 = FakeVersionedS3()
    s3.add(BASE + "private.txt", "v1")
    s3.inject_delete_errors = True
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="PURGE_ERRORS"):
        purge(s3)


def test_unacknowledged_version_delete_is_rejected():
    s3 = FakeVersionedS3()
    s3.add(BASE + "private.txt", "v1")
    s3.omit_ack = True
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="DELETE_UNCONFIRMED"):
        purge(s3)


def test_new_version_during_purge_must_not_be_reported_as_erased():
    s3 = FakeVersionedS3()
    s3.add(BASE + "private.txt", "v1")
    s3.race_reinsertion = True
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="REMAINING_AFTER_PURGE"):
        purge(s3)


@pytest.mark.parametrize(("org", "kb"), [(0, 10), (1, 0), (True, 10), (1, -1)])
def test_invalid_owner_scope_is_never_listed(org, kb):
    s3 = FakeVersionedS3()
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="SCOPE_INVALID"):
        m.delete_exclusive_shop_knowledge_versions(
            org, kb, client=s3, bucket="synthetic",
        )


def test_cross_prefix_version_list_poisoning_is_rejected_before_any_delete():
    class BadS3(FakeVersionedS3):
        def list_object_versions(self, **kwargs):
            return {"Versions": [{
                "Key": "organizations/9/knowledge-bases/10/documents/not-owned",
                "VersionId": "foreign-version",
            }], "IsTruncated": False}
    s3 = BadS3()
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="SCOPE_DRIFT"):
        purge(s3)
    assert s3.deletes == []


def test_duplicate_listed_version_id_fails_closed():
    class BadS3(FakeVersionedS3):
        def list_object_versions(self, **kwargs):
            item = {"Key": BASE + "private.txt", "VersionId": "v1"}
            return {"Versions": [item, dict(item)], "IsTruncated": False}
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="DUPLICATED"):
        purge(BadS3())


def test_pagination_loop_fails_without_removal():
    class LoopS3(FakeVersionedS3):
        def list_object_versions(self, **kwargs):
            return {
                "Versions": [{"Key": BASE + "private.txt", "VersionId": "v1"}],
                "IsTruncated": True,
                "NextKeyMarker": BASE + "private.txt",
                "NextVersionIdMarker": "v1",
            }
    s3 = LoopS3()
    with pytest.raises(m.ShopifyPrivacyS3VersionError, match="PAGINATION_LOOP|DUPLICATED"):
        purge(s3)
    assert s3.deletes == []
