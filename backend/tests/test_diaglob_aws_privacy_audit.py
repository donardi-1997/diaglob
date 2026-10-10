"""Pure stub-based tests; never access real AWS resources or credentials."""
from unittest.mock import Mock

from botocore.exceptions import ClientError

from tools.diaglob_aws_privacy_audit import audit, inspect_rag, inspect_s3


def aws_error(code):
    return ClientError(
        {"Error": {"Code": code, "Message": "Sensitive remote error ignored"}},
        "ReadOnlyInspection",
    )


def fixtures():
    lightsail = Mock()
    lightsail.get_instance.return_value = {
        "instance": {"state": {"name": "running"}, "addOns": []}
    }
    lightsail.get_auto_snapshots.return_value = {"autoSnapshots": []}
    lightsail.get_instance_snapshots.return_value = {
        "instanceSnapshots": []
    }

    s3 = Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.get_bucket_lifecycle_configuration.side_effect = aws_error(
        "NoSuchLifecycleConfiguration"
    )
    s3.list_objects_v2.return_value = {
        "Contents": [], "IsTruncated": False
    }
    s3.list_object_versions.return_value = {
        "Versions": [
            {"Key": "SECRET/PRIVATE-CUSTOMER", "IsLatest": False},
            {"Key": "SECRET/PRIVATE-CUSTOMER", "IsLatest": False},
        ],
        "DeleteMarkers": [
            {"Key": "SECRET/PRIVATE-CUSTOMER"},
            {"Key": "SECRET/PRIVATE-CUSTOMER"},
        ],
        "IsTruncated": False,
    }

    agent = Mock()
    agent.list_knowledge_bases.return_value = {
        "knowledgeBaseSummaries": [
            {"name": "diaglob-prod-org-1-kb-8", "knowledgeBaseId": "KB1", "status": "ACTIVE"},
            {"name": "unrelated-recruiter-kb", "knowledgeBaseId": "KB2", "status": "ACTIVE"},
        ]
    }
    agent.get_knowledge_base.return_value = {
        "knowledgeBase": {
            "storageConfiguration": {
                "s3VectorsConfiguration": {
                    "vectorBucketArn": "arn:aws:s3vectors:us-east-2:123:bucket/diaglob-vectors",
                    "indexArn": "arn:aws:s3vectors:us-east-2:123:bucket/diaglob-vectors/index/diaglob-kb-8",
                }
            }
        }
    }
    agent.list_data_sources.return_value = {
        "dataSourceSummaries": [{"name": "secret-source", "dataSourceId": "DS1"}]
    }
    vectors = Mock()
    vectors.list_vectors.return_value = {"vectors": []}

    class Session:
        clients = {
            "lightsail": lightsail,
            "s3": s3,
            "bedrock-agent": agent,
            "s3vectors": vectors,
        }

        def client(self, name, *, region_name):
            assert region_name == "us-east-2"
            return self.clients[name]

    return Session(), lightsail, s3, agent, vectors


def test_audit_identifies_backup_retention_and_rag_gaps_without_exposing_pii():
    session, lightsail, s3, agent, vectors = fixtures()
    result = audit(
        session, region="us-east-2", instance="diaglob-prod",
        bucket="diaglob-test-knowledge",
    )
    assert result["findings"] == [
        "ALL_DIAGLOB_VECTOR_INDEXES_EMPTY",
        "KNOWLEDGE_SOURCE_BUCKET_EMPTY",
        "LIGHTSAIL_AUTOSNAPSHOT_DISABLED",
        "NO_VERIFIED_LIGHTSAIL_RECOVERY_POINT",
        "VERSIONED_S3_WITHOUT_NONCURRENT_EXPIRATION",
    ]
    assert result["mode"] == "read_only"
    assert result["production_changes"] is False
    assert result["privacy_fulfillment_authorized"] is False
    assert result["checks"]["lightsail"]["automatic_snapshot_addon_enabled"] is False
    assert result["checks"]["lightsail"]["automatic_snapshot_count"] == 0
    assert result["checks"]["s3"]["lifecycle_configured"] is False
    assert result["checks"]["s3"]["noncurrent_versions_on_page"] == 2
    assert result["checks"]["s3"]["delete_markers_on_page"] == 2
    assert result["checks"]["bedrock"]["knowledge_bases"][0]["has_vectors"] is False
    assert "PRIVATE-CUSTOMER" not in str(result)
    assert "secret-source" not in str(result)
    assert len(result["checks"]["bedrock"]["knowledge_bases"]) == 1
    agent.get_knowledge_base.assert_called_once_with(knowledgeBaseId="KB1")
    vectors.list_vectors.assert_called_once_with(
        vectorBucketName="diaglob-vectors",
        indexName="diaglob-kb-8",
        maxResults=1,
        returnData=False,
        returnMetadata=False,
    )
    lightsail.create_instance_snapshot.assert_not_called()
    s3.put_bucket_lifecycle_configuration.assert_not_called()
    vectors.delete_vectors.assert_not_called()


def test_aws_access_denied_is_unverified_not_reported_as_missing_lifecycle():
    session, _, s3, _, _ = fixtures()
    s3.get_bucket_lifecycle_configuration.side_effect = aws_error("AccessDenied")
    result = audit(
        session, region="us-east-2", instance="diaglob-prod",
        bucket="diaglob-test-knowledge",
    )
    assert result["checks"]["s3"] == {
        "state": "unverified", "error_code": "AccessDenied"
    }
    assert result["checks"]["lightsail"]["state"] == "verified"


def test_incomplete_s3_metadata_page_is_labeled_incomplete():
    _, _, s3, _, _ = fixtures()
    s3.list_objects_v2.return_value = {
        "Contents": [{"Key": "secret", "Size": 1}],
        "IsTruncated": True,
    }
    s3.list_object_versions.return_value = {
        "Versions": [{"Key": "secret", "IsLatest": True}],
        "DeleteMarkers": [],
        "IsTruncated": True,
    }
    result = inspect_s3(s3, "diaglob-test-knowledge")
    assert result["current_object_count_on_page"] == 1
    assert result["current_objects_truncated"] is True
    assert result["version_history_truncated"] is True
    assert "secret" not in str(result)


def test_knowledge_base_without_vector_index_is_unknown_not_empty():
    _, _, _, agent, vectors = fixtures()
    agent.get_knowledge_base.return_value = {
        "knowledgeBase": {"storageConfiguration": {"type": "S3_VECTORS"}}
    }
    result = inspect_rag(agent, vectors)
    assert result["knowledge_bases"][0]["has_vectors"] is None
    vectors.list_vectors.assert_not_called()


def test_auto_snapshot_addon_reports_enabled_when_configured():
    session, lightsail, _, _, _ = fixtures()
    lightsail.get_instance.return_value = {
        "instance": {
            "state": {"name": "running"},
            "addOns": [{"name": "AutoSnapshot", "status": "Enabled"}],
        }
    }
    result = audit(
        session, region="us-east-2", instance="diaglob-prod",
        bucket="diaglob-test-knowledge",
    )
    assert result["checks"]["lightsail"]["automatic_snapshot_addon_enabled"] is True


def test_unverified_s3_never_becomes_healthy_or_claims_empty_source():
    session, _, s3, _, _ = fixtures()
    s3.get_bucket_versioning.side_effect = aws_error("AccessDenied")
    result = audit(
        session, region="us-east-2", instance="diaglob-prod",
        bucket="diaglob-test-knowledge",
    )
    assert result["checks"]["s3"]["state"] == "unverified"
    assert "KNOWLEDGE_SOURCE_BUCKET_EMPTY" not in result["findings"]
    assert "VERSIONED_S3_WITHOUT_NONCURRENT_EXPIRATION" not in result["findings"]


def test_disabled_lifecycle_rules_do_not_hide_s3_retention_gap():
    session, _, s3, _, _ = fixtures()
    s3.get_bucket_lifecycle_configuration.side_effect = None
    s3.get_bucket_lifecycle_configuration.return_value = {
        "Rules": [{
            "ID": "DisabledOldRule",
            "Status": "Disabled",
            "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
        }]
    }
    result = audit(
        session, region="us-east-2", instance="diaglob-prod",
        bucket="diaglob-test-knowledge",
    )
    assert result["checks"]["s3"]["lifecycle_configured"] is True
    assert result["checks"]["s3"]["active_noncurrent_expiration_rule_count"] == 0
    assert "VERSIONED_S3_WITHOUT_NONCURRENT_EXPIRATION" in result["findings"]
