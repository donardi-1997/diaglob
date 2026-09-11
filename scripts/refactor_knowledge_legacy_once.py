"""One-off rewrite of the Knowledge facade after extracting legacy cleanup."""
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "backend/app/bedrock_knowledge_base.py"
text = PATH.read_text()

text = text.replace(
    "from botocore.exceptions import BotoCoreError, ClientError\n",
    "",
)
text = text.replace(
    "from .models import KnowledgeBase, KnowledgeSource\n",
    "from .models import KnowledgeBase\n",
)

old_deletion_import = '''from .knowledge_provisioning.deletion import (\n    DeletionOperations,\n    cleanup_owned_resources,\n    delete_knowledge_base,\n)\n'''
new_deletion_import = old_deletion_import + '''from .knowledge_provisioning.legacy import (\n    LEGACY_KNOWLEDGE_INFRASTRUCTURE,\n    LegacyCleanupOperations,\n    cleanup_verified_legacy_resources as cleanup_legacy_resources,\n    is_verified_legacy_parent as legacy_parent_matches,\n    legacy_vector_index_arn,\n    validate_legacy_data_source_ownership as validate_legacy_ownership,\n)\n'''
if old_deletion_import not in text:
    raise SystemExit("deletion import block not found")
text = text.replace(old_deletion_import, new_deletion_import, 1)

old_constant = '''LEGACY_KNOWLEDGE_INFRASTRUCTURE = {\n    "bedrock_kb_id": "RDAQY1JNQ8",\n    "bedrock_kb_name": "diaglob-knowledge-main",\n    "vector_index_name": "diaglob-knowledge-v1",\n}\n\n'''
if old_constant not in text:
    raise SystemExit("legacy constant block not found")
text = text.replace(old_constant, "", 1)

start = text.index("def is_verified_legacy_parent(")
end = text.index("def _s3_vectors_adapter()", start)
replacement = '''def is_verified_legacy_parent(bedrock_kb_id: str) -> bool:\n    """Check if a Bedrock KB ID belongs to the known legacy infrastructure."""\n    return legacy_parent_matches(\n        bedrock_kb_id,\n        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,\n    )\n\n\ndef _legacy_vector_index_arn() -> str:\n    """Build the ARN for the legacy shared vector index."""\n    return legacy_vector_index_arn(\n        VECTOR_BUCKET_ARN,\n        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,\n    )\n\n\ndef validate_legacy_data_source_ownership(\n    remote_ds: dict[str, Any],\n    remote_kb: dict[str, Any],\n    org_id: int,\n    kb_id: int,\n) -> None:\n    """Verify a legacy Data Source is safe to delete."""\n    validate_legacy_ownership(\n        remote_ds,\n        remote_kb,\n        org_id,\n        kb_id,\n        legacy_kb_id=LEGACY_KNOWLEDGE_INFRASTRUCTURE["bedrock_kb_id"],\n        knowledge_bucket=KNOWLEDGE_BUCKET,\n        expected_prefix=_get_s3_prefix(org_id, kb_id),\n    )\n\n\ndef _delete_legacy_data_source(\n    bedrock_kb_id: str,\n    bedrock_ds_id: str,\n) -> Any:\n    return _get_bedrock_agent_client().delete_data_source(\n        knowledgeBaseId=bedrock_kb_id,\n        dataSourceId=bedrock_ds_id,\n    )\n\n\ndef _legacy_cleanup_operations() -> LegacyCleanupOperations:\n    """Capture the facade's current legacy cleanup dependencies at call time."""\n    return LegacyCleanupOperations(\n        get_knowledge_base=get_bedrock_knowledge_base,\n        get_data_source=get_bedrock_data_source,\n        delete_data_source=_delete_legacy_data_source,\n        validate_data_source_ownership=validate_legacy_data_source_ownership,\n        delete_knowledge_prefix=delete_knowledge_prefix,\n        commit_state=_commit_state,\n        sleep_between_attempts=_sleep_between_attempts,\n        client_error_code=_client_error_code,\n        log_aws_error=_log_provisioning_aws_error,\n        aws_provisioning_error=_aws_provisioning_error,\n    )\n\n\ndef cleanup_verified_legacy_resources(\n    db: Session,\n    knowledge_base: KnowledgeBase,\n) -> None:\n    """Delete only the verified legacy Data Source and local resources."""\n    cleanup_legacy_resources(\n        db,\n        knowledge_base,\n        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,\n        wait_attempts=WAIT_ATTEMPTS,\n        operations=_legacy_cleanup_operations(),\n    )\n\n\n'''
text = text[:start] + replacement + text[end:]

PATH.write_text(text)
