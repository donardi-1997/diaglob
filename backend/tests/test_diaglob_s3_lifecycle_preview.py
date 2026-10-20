"""Synthetic guard tests: lifecycle candidate is disabled, tenant-prefix bounded."""
import pytest

from tools.diaglob_s3_lifecycle_preview import make_disabled_lifecycle_rule


PREFIX = "organizations/1/knowledge-bases/8/documents/"


def test_preview_is_disabled_and_prefix_limited():
    result = make_disabled_lifecycle_rule(
        prefix=PREFIX, noncurrent_days=45, approval_reference="LEGAL-APPROVED-123"
    )
    assert result["Status"] == "Disabled"
    assert result["Filter"] == {"Prefix": PREFIX}
    assert result["NoncurrentVersionExpiration"] == {"NoncurrentDays": 45}
    assert "Expiration" not in result
    assert "AbortIncompleteMultipartUpload" not in result


@pytest.mark.parametrize("prefix", [
    "", "/", "organizations/", "organizations/1/",
    "organizations/1/knowledge-bases/8",
    "organizations/1/knowledge-bases/8/documents/../../",
    "org/1/docs/", "organizations/0/knowledge-bases/8/documents/",
    "organizations/1/knowledge-bases/8/documents/private/",
])
def test_rejects_blank_unscoped_and_path_traversal_prefix(prefix):
    with pytest.raises(ValueError, match="APPROVED_EXACT_KNOWLEDGE_PREFIX_REQUIRED"):
        make_disabled_lifecycle_rule(
            prefix=prefix, noncurrent_days=45, approval_reference="LEGAL-123"
        )


@pytest.mark.parametrize("days", [None, 0, -1, 3651, True, 15.5, "30"])
def test_requires_explicit_valid_duration(days):
    with pytest.raises(ValueError, match="APPROVED_NONCURRENT_RETENTION_DAYS_REQUIRED"):
        make_disabled_lifecycle_rule(
            prefix=PREFIX, noncurrent_days=days, approval_reference="LEGAL-123"
        )


@pytest.mark.parametrize("ref", ["", "P0", None, "approval with spaces", "bad/slug"])
def test_rejects_missing_or_unstructured_approval_reference(ref):
    with pytest.raises(ValueError, match="RETENTION_APPROVAL_REFERENCE_REQUIRED"):
        make_disabled_lifecycle_rule(
            prefix=PREFIX, noncurrent_days=45, approval_reference=ref
        )
