"""One-off refactor: delegate S3 Vectors operations to the infrastructure adapter."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "bedrock_knowledge_base.py"

TARGETS = {
    "get_s3_vectors_index",
    "_get_s3_vectors_tags",
    "_validate_s3_vectors_index",
    "_recover_s3_vectors_index",
    "create_s3_vectors_index",
    "delete_s3_vectors_index",
}

ERROR_IMPORT = '''from .knowledge_provisioning.errors import (\n    BedrockProvisioningError,\n    ProvisioningErrorClassification,\n    ProvisioningInProgressError,\n    _aws_provisioning_error,\n    _client_error_code,\n    _client_error_message,\n    _client_error_request_id,\n    _is_uncertain_create_error,\n    classify_provisioning_aws_error,\n)\n'''

ADAPTER_IMPORT = '''from .knowledge_provisioning.s3_vectors import (\n    S3VectorsAdapter,\n    S3VectorsConfig,\n)\n'''

WRAPPERS = '''def _s3_vectors_adapter() -> S3VectorsAdapter:\n    \"\"\"Build the S3 Vectors adapter from the current facade configuration.\n\n    Construction is intentionally lazy so existing tests and operational code that\n    patch the legacy module's configuration/client factory keep working unchanged.\n    \"\"\"\n    return S3VectorsAdapter(\n        config=S3VectorsConfig(\n            vector_bucket_arn=VECTOR_BUCKET_ARN,\n            environment=ENVIRONMENT,\n            vector_dimension=VECTOR_DIMENSION,\n            vector_data_type=VECTOR_DATA_TYPE,\n            vector_distance_metric=VECTOR_DISTANCE_METRIC,\n            non_filterable_metadata_keys=VECTOR_NON_FILTERABLE_METADATA_KEYS,\n            recovery_attempts=RECOVERY_ATTEMPTS,\n            wait_attempts=WAIT_ATTEMPTS,\n        ),\n        client_factory=_get_s3_vectors_client,\n        vector_index_arn=_vector_index_arn,\n        build_vector_index_name=build_vector_index_name,\n        make_tags=_make_tags,\n        tags_match=_tags_match,\n        sleep_between_attempts=_sleep_between_attempts,\n        validate_configuration=_validate_configuration,\n        log_aws_error=_log_provisioning_aws_error,\n    )\n\n\ndef get_s3_vectors_index(index_arn: str) -> dict[str, Any] | None:\n    return _s3_vectors_adapter().get_index(index_arn)\n\n\ndef _get_s3_vectors_tags(index_arn: str) -> dict[str, str]:\n    return _s3_vectors_adapter().get_tags(index_arn)\n\n\ndef _validate_s3_vectors_index(\n    index: dict[str, Any],\n    tags: dict[str, str],\n    org_id: int,\n    kb_id: int,\n) -> None:\n    _s3_vectors_adapter().validate_index(index, tags, org_id, kb_id)\n\n\ndef _recover_s3_vectors_index(org_id: int, kb_id: int) -> dict[str, Any] | None:\n    return _s3_vectors_adapter().recover_index(org_id, kb_id)\n\n\ndef create_s3_vectors_index(org_id: int, kb_id: int) -> dict[str, Any]:\n    return _s3_vectors_adapter().create_index(org_id, kb_id)\n\n\ndef delete_s3_vectors_index(index_arn: str, org_id: int, kb_id: int) -> None:\n    _s3_vectors_adapter().delete_index(index_arn, org_id, kb_id)\n\n\n'''


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if "def _s3_vectors_adapter()" in text:
        raise SystemExit("S3 Vectors adapter delegation already applied")
    if ERROR_IMPORT not in text:
        raise SystemExit("Expected Knowledge provisioning error import block not found")

    tree = ast.parse(text)
    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TARGETS:
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))

    found = {name for _, _, name in spans}
    missing = TARGETS - found
    if missing:
        raise SystemExit(f"Missing expected S3 Vectors functions: {sorted(missing)}")

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
    updated = updated.replace(ERROR_IMPORT, ERROR_IMPORT + ADAPTER_IMPORT, 1)

    direct_provider_markers = (
        "_get_s3_vectors_client().create_index(",
        "_get_s3_vectors_client().get_index(",
        "_get_s3_vectors_client().delete_index(",
        "_get_s3_vectors_client().list_tags_for_resource(",
    )
    if any(marker in updated for marker in direct_provider_markers):
        raise SystemExit("Direct S3 Vectors provider operation unexpectedly remains")

    ast.parse(updated)
    SOURCE.write_text(updated, encoding="utf-8")
    print(f"Delegated {len(TARGETS)} S3 Vectors functions to adapter")


if __name__ == "__main__":
    main()
