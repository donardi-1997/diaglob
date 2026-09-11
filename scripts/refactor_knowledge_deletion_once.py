"""One-off refactor: delegate Knowledge Base cleanup/deletion orchestration."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "bedrock_knowledge_base.py"

ORCHESTRATOR_IMPORT = '''from .knowledge_provisioning.orchestrator import (\n    ProvisioningOperations,\n    provision_knowledge_base,\n)\n'''

DELETION_IMPORT = '''from .knowledge_provisioning.deletion import (\n    DeletionOperations,\n    cleanup_owned_resources,\n    delete_knowledge_base,\n)\n'''

WRAPPERS = '''def _deletion_operations() -> DeletionOperations:\n    \"\"\"Capture the facade's current deletion callables at invocation time.\"\"\"\n    return DeletionOperations(\n        vector_index_arn=_vector_index_arn,\n        cleanup_remote_resources=_cleanup_remote_resources,\n        commit_state=_commit_state,\n        is_verified_legacy_parent=is_verified_legacy_parent,\n        cleanup_verified_legacy_resources=cleanup_verified_legacy_resources,\n        delete_knowledge_prefix=delete_knowledge_prefix,\n        client_error_code=_client_error_code,\n        client_error_message=_client_error_message,\n        client_error_request_id=_client_error_request_id,\n    )\n\n\ndef cleanup_bedrock_resources(\n    db: Session, knowledge_base: KnowledgeBase\n) -> None:\n    \"\"\"Safely clean owned resources without losing ambiguous remote IDs.\"\"\"\n    cleanup_owned_resources(\n        db,\n        knowledge_base,\n        operations=_deletion_operations(),\n    )\n\n\ndef delete_diaglob_knowledge_base(\n    db: Session, knowledge_base: KnowledgeBase\n) -> None:\n    \"\"\"Delete one KB and only its verified remote resources and S3 prefix.\"\"\"\n    delete_knowledge_base(\n        db,\n        knowledge_base,\n        operations=_deletion_operations(),\n    )\n'''

TARGETS = {"cleanup_bedrock_resources", "delete_diaglob_knowledge_base"}


def node_start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno] + [decorator.lineno for decorator in decorators])


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if DELETION_IMPORT in text:
        raise SystemExit("Deletion orchestrator delegation already applied")
    if ORCHESTRATOR_IMPORT not in text:
        raise SystemExit("Expected provisioning orchestrator import block not found")

    tree = ast.parse(text)
    spans = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TARGETS:
            spans.append((node_start(node), node.end_lineno or node.lineno, node.name))

    found = {name for _, _, name in spans}
    if found != TARGETS:
        raise SystemExit(f"Expected deletion functions not found exactly once: {sorted(found)}")

    first_line = min(start for start, _, _ in spans)
    lines = text.splitlines(keepends=True)
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start - 1 : end]
    updated = "".join(lines)
    updated = updated.replace(ORCHESTRATOR_IMPORT, ORCHESTRATOR_IMPORT + DELETION_IMPORT, 1)

    # Preserve the historical public functions as thin call-time wrappers.
    tree_after_removal = ast.parse(updated)
    insertion_index = None
    for node in tree_after_removal.body:
        if isinstance(node, ast.FunctionDef) and node.lineno >= first_line:
            insertion_index = node.lineno - 1
            break
    if insertion_index is None:
        updated = updated.rstrip() + "\n\n" + WRAPPERS + "\n"
    else:
        new_lines = updated.splitlines(keepends=True)
        new_lines[insertion_index:insertion_index] = [WRAPPERS + "\n\n"]
        updated = "".join(new_lines)

    # datetime/timezone lived in the facade only for the two extracted flows.
    updated = updated.replace("from datetime import datetime, timezone\n", "", 1)

    parsed = ast.parse(updated)
    names = {
        node.name
        for node in parsed.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_deletion_operations", *TARGETS}
    }
    expected = {"_deletion_operations", *TARGETS}
    if names != expected:
        raise SystemExit(f"Unexpected deletion facade boundary: {sorted(names)}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("Delegated Knowledge Base cleanup/deletion orchestration")


if __name__ == "__main__":
    main()
