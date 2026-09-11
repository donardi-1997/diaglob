"""One-off refactor: move modern remote cleanup coordination behind a boundary."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "bedrock_knowledge_base.py"

LIFECYCLE_IMPORT = '''from .knowledge_provisioning.lifecycle import (\n    _as_utc,\n    _claim_provisioning,\n    _commit_state,\n    _set_provisioning_stage,\n)\n'''

CLEANUP_IMPORT = '''from .knowledge_provisioning.cleanup import (\n    CleanupResult,\n    cleanup_remote_resources,\n)\n'''

WRAPPER = '''def _cleanup_remote_resources(\n    org_id: int,\n    kb_id: int,\n    index_arn: str | None,\n    bedrock_kb_id: str | None,\n    bedrock_ds_id: str | None,\n) -> CleanupResult:\n    return cleanup_remote_resources(\n        org_id,\n        kb_id,\n        index_arn,\n        bedrock_kb_id,\n        bedrock_ds_id,\n        delete_data_source=delete_bedrock_data_source,\n        delete_knowledge_base=delete_bedrock_knowledge_base,\n        delete_vector_index=delete_s3_vectors_index,\n    )\n\n\n'''


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if CLEANUP_IMPORT in text:
        raise SystemExit("Knowledge cleanup extraction already applied")
    if LIFECYCLE_IMPORT not in text:
        raise SystemExit("Expected lifecycle import block not found")

    tree = ast.parse(text)
    targets = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "CleanupResult":
            targets.append((node.lineno, node.end_lineno or node.lineno, node.name))
        if isinstance(node, ast.FunctionDef) and node.name == "_cleanup_remote_resources":
            targets.append((node.lineno, node.end_lineno or node.lineno, node.name))

    found = {name for _, _, name in targets}
    expected = {"CleanupResult", "_cleanup_remote_resources"}
    if found != expected:
        raise SystemExit(f"Expected cleanup definitions not found exactly once: {sorted(found)}")

    lines = text.splitlines(keepends=True)
    for start, end, _ in sorted(targets, reverse=True):
        del lines[start - 1 : end]
    updated = "".join(lines)
    updated = updated.replace("from dataclasses import dataclass\n", "", 1)
    updated = updated.replace(LIFECYCLE_IMPORT, LIFECYCLE_IMPORT + CLEANUP_IMPORT, 1)

    marker = "def provision_diaglob_knowledge_base(\n"
    if marker not in updated:
        raise SystemExit("Provisioning entry point marker not found")
    updated = updated.replace(marker, WRAPPER + marker, 1)

    tree_after = ast.parse(updated)
    local_cleanup_classes = [
        node for node in tree_after.body
        if isinstance(node, ast.ClassDef) and node.name == "CleanupResult"
    ]
    local_cleanup_functions = [
        node for node in tree_after.body
        if isinstance(node, ast.FunctionDef) and node.name == "_cleanup_remote_resources"
    ]
    if local_cleanup_classes or len(local_cleanup_functions) != 1:
        raise SystemExit("Unexpected cleanup boundary shape after refactor")

    SOURCE.write_text(updated, encoding="utf-8")
    print("Extracted modern remote cleanup coordination")


if __name__ == "__main__":
    main()
