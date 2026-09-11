"""One-off rewrite of the Knowledge facade to delegate pure configuration rules."""
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "backend/app/bedrock_knowledge_base.py"
text = PATH.read_text()

text = text.replace("import hashlib\n", "")
text = text.replace("import re\n", "")

legacy_import = '''from .knowledge_provisioning.legacy import (\n    LEGACY_KNOWLEDGE_INFRASTRUCTURE,\n    LegacyCleanupOperations,\n    cleanup_verified_legacy_resources as cleanup_legacy_resources,\n    is_verified_legacy_parent as legacy_parent_matches,\n    legacy_vector_index_arn,\n    validate_legacy_data_source_ownership as validate_legacy_ownership,\n)\n'''
config_import = legacy_import + '''from .knowledge_provisioning.configuration import (\n    KnowledgeProvisioningConfig,\n    VECTOR_DATA_TYPE,\n    VECTOR_DIMENSION,\n    VECTOR_DISTANCE_METRIC,\n    VECTOR_EMBEDDING_DATA_TYPE,\n    VECTOR_NON_FILTERABLE_METADATA_KEYS,\n    build_vector_index_name as config_build_vector_index_name,\n    environment_slug as config_environment_slug,\n    get_s3_prefix as config_get_s3_prefix,\n    make_client_token as config_make_client_token,\n    make_ds_name as config_make_ds_name,\n    make_kb_name as config_make_kb_name,\n    make_tags as config_make_tags,\n    missing_configuration,\n    normalize_environment as config_normalize_environment,\n    validate_configuration as config_validate_configuration,\n    vector_index_arn as config_vector_index_arn,\n)\n'''
if legacy_import not in text:
    raise SystemExit("legacy import block not found")
text = text.replace(legacy_import, config_import, 1)

start = text.index("_CANONICAL_ENVIRONMENTS = {")
end = text.index("PROVISIONING_STATES =", start)
replacement = '''def normalize_environment(value: str | None) -> str:\n    """Map a DIAGLOB_ENVIRONMENT value to a canonical form."""\n    return config_normalize_environment(value)\n\n\n_RAW_ENVIRONMENT = os.getenv("DIAGLOB_ENVIRONMENT")\n\n\ndef _resolve_environment(raw: str | None) -> str:\n    """Resolve and canonicalize the environment at provisioning time."""\n    return normalize_environment(raw)\n\n\nENVIRONMENT: str = (\n    _resolve_environment(_RAW_ENVIRONMENT) if _RAW_ENVIRONMENT else ""\n)\nVECTOR_BUCKET_ARN = os.getenv("DIAGLOB_VECTOR_BUCKET_ARN", "").strip()\nBEDROCK_SERVICE_ROLE_ARN = os.getenv("BEDROCK_SERVICE_ROLE_ARN", "").strip()\nEMBEDDING_MODEL_ARN = os.getenv(\n    "BEDROCK_EMBEDDING_MODEL_ARN",\n    f"arn:aws:bedrock:{AWS_REGION}::foundation-model/amazon.titan-embed-text-v2:0",\n).strip()\nKNOWLEDGE_BUCKET = os.getenv("DIAGLOB_KNOWLEDGE_BUCKET", "").strip()\n\n\n'''
text = text[:start] + replacement + text[end:]

start = text.index("def _environment_slug(")
end = text.index("def _log_provisioning_aws_error(", start)
replacement = '''def _environment_slug(environment: str) -> str:\n    return config_environment_slug(environment)\n\n\ndef build_vector_index_name(environment: str, kb_id: int) -> str:\n    """Build a deterministic, non-PII S3 Vectors index name."""\n    return config_build_vector_index_name(environment, kb_id)\n\n\ndef _make_kb_name(org_id: int, kb_id: int) -> str:\n    return config_make_kb_name(ENVIRONMENT, org_id, kb_id)\n\n\ndef _make_ds_name(kb_id: int) -> str:\n    return config_make_ds_name(ENVIRONMENT, kb_id)\n\n\ndef _make_client_token(prefix: str, org_id: int, kb_id: int) -> str:\n    return config_make_client_token(ENVIRONMENT, prefix, org_id, kb_id)\n\n\ndef _make_tags(org_id: int, kb_id: int) -> dict[str, str]:\n    return config_make_tags(ENVIRONMENT, org_id, kb_id)\n\n\ndef _get_s3_prefix(org_id: int, kb_id: int) -> str:\n    return config_get_s3_prefix(org_id, kb_id)\n\n\ndef _vector_index_arn(kb_id: int) -> str:\n    return config_vector_index_arn(VECTOR_BUCKET_ARN, ENVIRONMENT, kb_id)\n\n\ndef _current_provisioning_config() -> KnowledgeProvisioningConfig:\n    """Capture current facade settings so monkeypatched runtime values remain live."""\n    return KnowledgeProvisioningConfig(\n        environment=ENVIRONMENT,\n        vector_bucket_arn=VECTOR_BUCKET_ARN,\n        bedrock_service_role_arn=BEDROCK_SERVICE_ROLE_ARN,\n        embedding_model_arn=EMBEDDING_MODEL_ARN,\n        knowledge_bucket=KNOWLEDGE_BUCKET,\n    )\n\n\ndef _validate_configuration() -> None:\n    config = _current_provisioning_config()\n    missing = missing_configuration(config)\n    if missing:\n        logger.error(\n            "Missing Bedrock provisioning configuration: %s",\n            ", ".join(missing),\n        )\n    config_validate_configuration(config)\n\n\n'''
text = text[:start] + replacement + text[end:]

PATH.write_text(text)
