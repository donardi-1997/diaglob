"""Read-only AWS recovery, retention, and RAG evidence for Diaglob.

This program NEVER reads S3 object contents, vector contents/metadata, private
application logs, database rows or AWS secret values. It performs no writes.
Unknown API states remain "unverified", never silently treated as healthy.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import boto3
from botocore.exceptions import ClientError

NO_LIFECYCLE = "NoSuchLifecycleConfiguration"


def _aws_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", "AWS_API_ERROR"))


def inspect_lightsail(client: Any, name: str) -> dict:
    instance = client.get_instance(instanceName=name)["instance"]
    snapshots = client.get_auto_snapshots(resourceName=name).get("autoSnapshots", [])
    all_manual = client.get_instance_snapshots().get("instanceSnapshots", [])
    matching = [s for s in all_manual if s.get("fromInstanceName") == name]
    addons = instance.get("addOns", [])
    return {
        "state": "verified",
        "instance_state": instance.get("state", {}).get("name"),
        "automatic_snapshot_addon_enabled": any(
            a.get("name") == "AutoSnapshot" and a.get("status") == "Enabled"
            for a in addons
        ),
        "automatic_snapshot_count": len(snapshots),
        "manual_snapshot_count": len(matching),
    }


def inspect_s3(client: Any, bucket: str) -> dict:
    status = client.get_bucket_versioning(Bucket=bucket).get("Status")
    try:
        rules = client.get_bucket_lifecycle_configuration(Bucket=bucket).get(
            "Rules", []
        )
        lifecycle_configured = bool(rules)
    except ClientError as exc:
        if _aws_code(exc) != NO_LIFECYCLE:
            raise
        lifecycle_configured = False

    # Intentionally inspect only one bounded metadata page. Never print keys.
    current = client.list_objects_v2(Bucket=bucket, MaxKeys=1000)
    historical = client.list_object_versions(Bucket=bucket, MaxKeys=1000)
    versions = historical.get("Versions", [])
    return {
        "state": "verified",
        "versioning": status or "Unversioned",
        "lifecycle_configured": lifecycle_configured,
        "current_object_count_on_page": len(current.get("Contents", [])),
        "current_objects_truncated": bool(current.get("IsTruncated")),
        "noncurrent_versions_on_page": sum(
            v.get("IsLatest") is not True for v in versions
        ),
        "delete_markers_on_page": len(historical.get("DeleteMarkers", [])),
        "version_history_truncated": bool(historical.get("IsTruncated")),
    }


def inspect_rag(agent: Any, vectors: Any) -> dict:
    result = agent.list_knowledge_bases(maxResults=100)
    kb_items = [
        item for item in result.get("knowledgeBaseSummaries", [])
        if (item.get("name") or "").startswith("diaglob")
    ]
    knowledge_bases = []
    for summary in kb_items:
        kb_id = summary["knowledgeBaseId"]
        configuration = agent.get_knowledge_base(
            knowledgeBaseId=kb_id
        )["knowledgeBase"].get("storageConfiguration", {})
        storage = configuration.get("s3VectorsConfiguration") or {}
        index_arn = storage.get("indexArn", "")
        bucket_arn = storage.get("vectorBucketArn", "")
        index_name = index_arn.rsplit("/index/", 1)[-1] if "/index/" in index_arn else None
        bucket_name = (
            bucket_arn.rsplit("/bucket/", 1)[-1]
            if "/bucket/" in bucket_arn else None
        )
        sources = agent.list_data_sources(
            knowledgeBaseId=kb_id, maxResults=100
        )
        has_vectors: bool | None = None
        if index_name and bucket_name:
            sample = vectors.list_vectors(
                vectorBucketName=bucket_name,
                indexName=index_name,
                maxResults=1,
                returnData=False,
                returnMetadata=False,
            )
            has_vectors = bool(sample.get("vectors"))
        knowledge_bases.append({
            "knowledge_base_id": kb_id,
            "status": summary.get("status"),
            "data_source_count_on_page": len(sources.get("dataSourceSummaries", [])),
            "data_sources_truncated": bool(sources.get("nextToken")),
            "has_vectors": has_vectors,
        })
    return {
        "state": "verified",
        "knowledge_bases": knowledge_bases,
        "knowledge_bases_truncated": bool(result.get("nextToken")),
    }


def audit(session: Any, *, region: str, instance: str, bucket: str) -> dict:
    """Read-only independent checks; failures must be visible, not hidden."""
    results: dict[str, dict] = {}
    checks = {
        "lightsail": lambda: inspect_lightsail(
            session.client("lightsail", region_name=region), instance
        ),
        "s3": lambda: inspect_s3(
            session.client("s3", region_name=region), bucket
        ),
        "bedrock": lambda: inspect_rag(
            session.client("bedrock-agent", region_name=region),
            session.client("s3vectors", region_name=region),
        ),
    }
    for label, run in checks.items():
        try:
            results[label] = run()
        except ClientError as exc:
            results[label] = {"state": "unverified", "error_code": _aws_code(exc)}
        except (KeyError, ValueError, TypeError, AttributeError):
            results[label] = {"state": "unverified", "error_code": "INVALID_AWS_RESPONSE"}
    return {
        "mode": "read_only",
        "region": region,
        "instance": instance,
        "bucket": bucket,
        "checks": results,
        "production_changes": False,
        "privacy_fulfillment_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only DIAGLOB AWS backup/S3/Bedrock audit"
    )
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--instance", default="diaglob-prod")
    parser.add_argument(
        "--bucket", default="diaglob-knowledge-765761474007-us-east-2"
    )
    args = parser.parse_args()
    report = audit(
        boto3.Session(region_name=args.region),
        region=args.region,
        instance=args.instance,
        bucket=args.bucket,
    )
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if all(
        result.get("state") == "verified"
        for result in report["checks"].values()
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
