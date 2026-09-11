"""One-off refactor: delegate Knowledge Base provisioning orchestration."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "bedrock_knowledge_base.py"

CLEANUP_IMPORT = '''from .knowledge_provisioning.cleanup import (\n    CleanupResult,\n    cleanup_remote_resources,\n)\n'''

ORCHESTRATOR_IMPORT = '''from .knowledge_provisioning.orchestrator import (\n    ProvisioningOperations,\n    provision_knowledge_base,\n)\n'''

WRAPPER = '''def _provisioning_operations() -> ProvisioningOperations:\n    \"\"\"Capture the facade's current provisioning callables at invocation time.\"\"\"\n    return ProvisioningOperations(\n        claim_provisioning=_claim_provisioning,\n        create_vector_index=create_s3_vectors_index,\n        set_stage=_set_provisioning_stage,\n        get_knowledge_base=get_bedrock_knowledge_base,\n        wait_for_knowledge_base=wait_for_bedrock_knowledge_base,\n        create_knowledge_base=create_bedrock_knowledge_base,\n        commit_state=_commit_state,\n        get_data_source=get_bedrock_data_source,\n        wait_for_data_source=wait_for_bedrock_data_source,\n        create_data_source=create_bedrock_data_source,\n        cleanup_remote_resources=_cleanup_remote_resources,\n        as_utc=_as_utc,\n    )\n\n\ndef provision_diaglob_knowledge_base(\n    db: Session, knowledge_base: KnowledgeBase\n) -> tuple[str, str]:\n    \"\"\"Provision one isolated index, Bedrock KB, and Data Source.\"\"\"\n    return provision_knowledge_base(\n        db,\n        knowledge_base,\n        operations=_provisioning_operations(),\n    )\n\n\n'''


def node_start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno] + [decorator.lineno for decorator in decorators])


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if ORCHESTRATOR_IMPORT in text:
        raise SystemExit("Provisioning orchestrator delegation already applied")
    if CLEANUP_IMPORT not in text:
        raise SystemExit("Expected cleanup import block not found")

    tree = ast.parse(text)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "provision_diaglob_knowledge_base"
    ]
    if len(matches) != 1:
        raise SystemExit(f"Expected one provisioning function, found {len(matches)}")

    node = matches[0]
    start = node_start(node)
    end = node.end_lineno or node.lineno
    lines = text.splitlines(keepends=True)
    del lines[start - 1 : end]
    updated = "".join(lines)
    updated = updated.replace(CLEANUP_IMPORT, CLEANUP_IMPORT + ORCHESTRATOR_IMPORT, 1)

    marker = "def cleanup_bedrock_resources("
    if marker not in updated:
        raise SystemExit("Cleanup entry point marker not found")
    updated = updated.replace(marker, WRAPPER + marker, 1)

    tree_after = ast.parse(updated)
    provisioning_defs = [
        item
        for item in tree_after.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "provision_diaglob_knowledge_base"
    ]
    operation_defs = [
        item
        for item in tree_after.body
        if isinstance(item, ast.FunctionDef) and item.name == "_provisioning_operations"
    ]
    if len(provisioning_defs) != 1 or len(operation_defs) != 1:
        raise SystemExit("Unexpected facade orchestration boundary shape")

    SOURCE.write_text(updated, encoding="utf-8")
    print("Delegated Knowledge Base provisioning orchestration")


if __name__ == "__main__":
    main()
