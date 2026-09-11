"""One-off extraction of Knowledge provisioning error helpers."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "bedrock_knowledge_base.py"

TARGETS = {
    "BedrockProvisioningError",
    "ProvisioningInProgressError",
    "ProvisioningErrorClassification",
    "classify_provisioning_aws_error",
    "_find_client_error",
    "_client_error_code",
    "_client_error_message",
    "_client_error_request_id",
    "_aws_provisioning_error",
    "_is_uncertain_create_error",
}

IMPORT_BLOCK = '''from .knowledge_provisioning.errors import (\n    BedrockProvisioningError,\n    ProvisioningErrorClassification,\n    ProvisioningInProgressError,\n    _aws_provisioning_error,\n    _client_error_code,\n    _client_error_message,\n    _client_error_request_id,\n    _is_uncertain_create_error,\n    classify_provisioning_aws_error,\n)\n'''


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if "from .knowledge_provisioning.errors import (" in text:
        raise SystemExit("Error extraction already applied")

    tree = ast.parse(text)
    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in TARGETS:
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))

    found = {name for _, _, name in spans}
    missing = TARGETS - found
    if missing:
        raise SystemExit(f"Missing expected definitions: {sorted(missing)}")

    lines = text.splitlines(keepends=True)
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start - 1 : end]

    updated = "".join(lines)
    updated = updated.replace("from enum import Enum\n", "")
    anchor = "from .knowledge_storage import delete_knowledge_prefix\n"
    if anchor not in updated:
        raise SystemExit("Import anchor not found")
    updated = updated.replace(anchor, anchor + IMPORT_BLOCK, 1)

    for name in TARGETS:
        if f"class {name}" in updated or f"def {name}(" in updated:
            raise SystemExit(f"Definition unexpectedly remains: {name}")

    SOURCE.write_text(updated, encoding="utf-8")
    print(f"Extracted {len(TARGETS)} error definitions/helpers")


if __name__ == "__main__":
    main()
