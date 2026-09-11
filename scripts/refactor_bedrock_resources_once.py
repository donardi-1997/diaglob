"""One-off refactor: delegate modern Bedrock resource operations to an adapter."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "bedrock_knowledge_base.py"

TARGETS = {
    "get_bedrock_knowledge_base",
    "_get_bedrock_tags",
    "_validate_bedrock_knowledge_base",
    "_list_knowledge_bases_by_name",
    "discover_bedrock_knowledge_base",
    "create_bedrock_knowledge_base",
    "wait_for_bedrock_knowledge_base",
    "get_bedrock_data_source",
    "_validate_bedrock_data_source",
    "discover_bedrock_data_source",
    "create_bedrock_data_source",
    "wait_for_bedrock_data_source",
    "delete_bedrock_data_source",
    "delete_bedrock_knowledge_base",
}

S3_IMPORT = '''from .knowledge_provisioning.s3_vectors import (\n    S3VectorsAdapter,\n    S3VectorsConfig,\n)\n'''

ADAPTER_IMPORT = '''from .knowledge_provisioning.bedrock_resources import (\n    BedrockResourcesAdapter,\n    BedrockResourcesConfig,\n)\n'''

WRAPPERS = '''def _bedrock_resources_adapter() -> BedrockResourcesAdapter:\n    \"\"\"Build the modern Bedrock adapter from current facade configuration.\"\"\"\n    return BedrockResourcesAdapter(\n        config=BedrockResourcesConfig(\n            vector_bucket_arn=VECTOR_BUCKET_ARN,\n            bedrock_service_role_arn=BEDROCK_SERVICE_ROLE_ARN,\n            embedding_model_arn=EMBEDDING_MODEL_ARN,\n            knowledge_bucket=KNOWLEDGE_BUCKET,\n            vector_dimension=VECTOR_DIMENSION,\n            vector_embedding_data_type=VECTOR_EMBEDDING_DATA_TYPE,\n            recovery_attempts=RECOVERY_ATTEMPTS,\n            wait_attempts=WAIT_ATTEMPTS,\n        ),\n        client_factory=_get_bedrock_agent_client,\n        make_kb_name=_make_kb_name,\n        make_ds_name=_make_ds_name,\n        make_client_token=_make_client_token,\n        make_tags=_make_tags,\n        tags_match=_tags_match,\n        get_s3_prefix=_get_s3_prefix,\n        vector_index_arn=_vector_index_arn,\n        validate_configuration=_validate_configuration,\n        sleep_between_attempts=_sleep_between_attempts,\n        log_aws_error=_log_provisioning_aws_error,\n    )\n\n\ndef get_bedrock_knowledge_base(bedrock_kb_id: str) -> dict[str, Any] | None:\n    return _bedrock_resources_adapter().get_knowledge_base(bedrock_kb_id)\n\n\ndef _get_bedrock_tags(resource_arn: str) -> dict[str, str]:\n    return _bedrock_resources_adapter().get_tags(resource_arn)\n\n\ndef _validate_bedrock_knowledge_base(\n    remote: dict[str, Any], org_id: int, kb_id: int, index_arn: str\n) -> None:\n    _bedrock_resources_adapter().validate_knowledge_base(\n        remote, org_id, kb_id, index_arn\n    )\n\n\ndef _list_knowledge_bases_by_name(name: str) -> list[dict[str, Any]]:\n    return _bedrock_resources_adapter()._list_knowledge_bases_by_name(name)\n\n\ndef discover_bedrock_knowledge_base(\n    org_id: int, kb_id: int, index_arn: str\n) -> dict[str, Any] | None:\n    return _bedrock_resources_adapter().discover_knowledge_base(\n        org_id, kb_id, index_arn\n    )\n\n\ndef create_bedrock_knowledge_base(\n    org_id: int,\n    kb_id: int,\n    index_arn: str,\n    description: str | None = None,\n) -> dict[str, Any]:\n    return _bedrock_resources_adapter().create_knowledge_base(\n        org_id, kb_id, index_arn, description\n    )\n\n\ndef wait_for_bedrock_knowledge_base(\n    bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str\n) -> dict[str, Any]:\n    return _bedrock_resources_adapter().wait_for_knowledge_base(\n        bedrock_kb_id, org_id, kb_id, index_arn\n    )\n\n\ndef get_bedrock_data_source(\n    bedrock_kb_id: str, data_source_id: str\n) -> dict[str, Any] | None:\n    return _bedrock_resources_adapter().get_data_source(\n        bedrock_kb_id, data_source_id\n    )\n\n\ndef _validate_bedrock_data_source(\n    remote: dict[str, Any], bedrock_kb_id: str, org_id: int, kb_id: int\n) -> None:\n    _bedrock_resources_adapter().validate_data_source(\n        remote, bedrock_kb_id, org_id, kb_id\n    )\n\n\ndef discover_bedrock_data_source(\n    bedrock_kb_id: str, org_id: int, kb_id: int\n) -> dict[str, Any] | None:\n    return _bedrock_resources_adapter().discover_data_source(\n        bedrock_kb_id, org_id, kb_id\n    )\n\n\ndef create_bedrock_data_source(\n    bedrock_kb_id: str, org_id: int, kb_id: int\n) -> dict[str, Any]:\n    return _bedrock_resources_adapter().create_data_source(\n        bedrock_kb_id, org_id, kb_id\n    )\n\n\ndef wait_for_bedrock_data_source(\n    bedrock_kb_id: str, data_source_id: str, org_id: int, kb_id: int\n) -> dict[str, Any]:\n    return _bedrock_resources_adapter().wait_for_data_source(\n        bedrock_kb_id, data_source_id, org_id, kb_id\n    )\n\n\ndef delete_bedrock_data_source(\n    bedrock_kb_id: str,\n    data_source_id: str,\n    org_id: int,\n    kb_id: int,\n    index_arn: str,\n) -> None:\n    _bedrock_resources_adapter().delete_data_source(\n        bedrock_kb_id, data_source_id, org_id, kb_id, index_arn\n    )\n\n\ndef delete_bedrock_knowledge_base(\n    bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str\n) -> None:\n    _bedrock_resources_adapter().delete_knowledge_base(\n        bedrock_kb_id, org_id, kb_id, index_arn\n    )\n\n\n'''


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if "def _bedrock_resources_adapter()" in text:
        raise SystemExit("Bedrock resource adapter delegation already applied")
    if S3_IMPORT not in text:
        raise SystemExit("Expected S3 Vectors adapter import block not found")

    tree = ast.parse(text)
    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TARGETS:
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))

    found = {name for _, _, name in spans}
    missing = TARGETS - found
    if missing:
        raise SystemExit(f"Missing expected Bedrock resource functions: {sorted(missing)}")

    first_line = min(start for start, _, _ in spans)
    lines = text.splitlines(keepends=True)
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start - 1 : end]

    removed_before = sum(
        end - start + 1 for start, end, _ in spans if end < first_line
    )
    insertion_index = first_line - 1 - removed_before
    lines[insertion_index:insertion_index] = [WRAPPERS]
    updated = "".join(lines)
    updated = updated.replace(S3_IMPORT, S3_IMPORT + ADAPTER_IMPORT, 1)

    # The legacy deletion path intentionally retains one direct provider delete call;
    # modern create/get/list/delete operations must otherwise be delegated.
    modern_markers = (
        "_get_bedrock_agent_client().create_knowledge_base(",
        "_get_bedrock_agent_client().create_data_source(",
        "_get_bedrock_agent_client().delete_knowledge_base(",
        "_get_bedrock_agent_client().get_knowledge_base(",
        "_get_bedrock_agent_client().get_data_source(",
        "client.list_knowledge_bases(",
        "client.list_data_sources(",
    )
    if any(marker in updated for marker in modern_markers):
        raise SystemExit("Modern direct Bedrock provider operation unexpectedly remains")

    ast.parse(updated)
    SOURCE.write_text(updated, encoding="utf-8")
    print(f"Delegated {len(TARGETS)} modern Bedrock resource functions")


if __name__ == "__main__":
    main()
