"""One-off rewrite of Knowledge facade runtime helpers."""
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "backend/app/bedrock_knowledge_base.py"
text = PATH.read_text()

text = text.replace("import time\n", "")

config_import = '''from .knowledge_provisioning.configuration import (\n    KnowledgeProvisioningConfig,\n    VECTOR_DATA_TYPE,\n    VECTOR_DIMENSION,\n    VECTOR_DISTANCE_METRIC,\n    VECTOR_EMBEDDING_DATA_TYPE,\n    VECTOR_NON_FILTERABLE_METADATA_KEYS,\n    build_vector_index_name as config_build_vector_index_name,\n    environment_slug as config_environment_slug,\n    get_s3_prefix as config_get_s3_prefix,\n    make_client_token as config_make_client_token,\n    make_ds_name as config_make_ds_name,\n    make_kb_name as config_make_kb_name,\n    make_tags as config_make_tags,\n    missing_configuration,\n    normalize_environment as config_normalize_environment,\n    validate_configuration as config_validate_configuration,\n    vector_index_arn as config_vector_index_arn,\n)\n'''
runtime_import = config_import + '''from .knowledge_provisioning.runtime import (\n    AwsDiagnosticsContext,\n    log_provisioning_aws_error as runtime_log_provisioning_aws_error,\n    sleep_between_attempts as runtime_sleep_between_attempts,\n    tags_match as runtime_tags_match,\n)\n'''
if config_import not in text:
    raise SystemExit("configuration import block not found")
text = text.replace(config_import, runtime_import, 1)

start = text.index("def _log_provisioning_aws_error(")
end = text.index("def is_verified_legacy_parent(", start)
replacement = '''def _diagnostics_context() -> AwsDiagnosticsContext:\n    """Capture current facade values used in structured AWS diagnostics."""\n    return AwsDiagnosticsContext(\n        vector_bucket_arn=VECTOR_BUCKET_ARN,\n        bedrock_service_role_arn=BEDROCK_SERVICE_ROLE_ARN,\n        embedding_model_arn=EMBEDDING_MODEL_ARN,\n        knowledge_bucket=KNOWLEDGE_BUCKET,\n    )\n\n\ndef _log_provisioning_aws_error(\n    *,\n    operation: str,\n    aws_service: str,\n    stage: str,\n    org_id: int,\n    kb_id: int,\n    error: Exception,\n    vector_index_arn: str | None = None,\n    bedrock_kb_id: str | None = None,\n    bedrock_data_source_id: str | None = None,\n) -> None:\n    runtime_log_provisioning_aws_error(\n        logger=logger,\n        operation=operation,\n        aws_service=aws_service,\n        stage=stage,\n        org_id=org_id,\n        kb_id=kb_id,\n        error=error,\n        context=_diagnostics_context(),\n        client_error_code=_client_error_code,\n        client_error_message=_client_error_message,\n        client_error_request_id=_client_error_request_id,\n        vector_index_arn=vector_index_arn,\n        bedrock_kb_id=bedrock_kb_id,\n        bedrock_data_source_id=bedrock_data_source_id,\n    )\n\n\ndef _sleep_between_attempts(attempt: int, attempts: int) -> None:\n    runtime_sleep_between_attempts(\n        attempt,\n        attempts,\n        POLL_INTERVAL_SECONDS,\n    )\n\n\ndef _tags_match(actual: dict[str, str], expected: dict[str, str]) -> bool:\n    return runtime_tags_match(actual, expected)\n\n\n'''
text = text[:start] + replacement + text[end:]

PATH.write_text(text)
