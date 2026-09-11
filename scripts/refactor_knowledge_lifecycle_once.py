"""One-off refactor: move transactional provisioning lifecycle helpers."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "bedrock_knowledge_base.py"

TARGETS = {
    "_commit_state",
    "_set_provisioning_stage",
    "_as_utc",
    "_claim_provisioning",
}

ANCHOR = '''from .knowledge_provisioning.bedrock_resources import (\n    BedrockResourcesAdapter,\n    BedrockResourcesConfig,\n)\n'''

IMPORT_BLOCK = '''from .knowledge_provisioning.lifecycle import (\n    _as_utc,\n    _claim_provisioning,\n    _commit_state,\n    _set_provisioning_stage,\n)\n'''


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if "from .knowledge_provisioning.lifecycle import (" in text:
        raise SystemExit("Knowledge lifecycle extraction already applied")
    if ANCHOR not in text:
        raise SystemExit("Expected Bedrock resource adapter import block not found")

    tree = ast.parse(text)
    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TARGETS:
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))

    found = {name for _, _, name in spans}
    missing = TARGETS - found
    if missing:
        raise SystemExit(f"Missing expected lifecycle helpers: {sorted(missing)}")

    lines = text.splitlines(keepends=True)
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start - 1 : end]
    updated = "".join(lines)
    updated = updated.replace(ANCHOR, ANCHOR + IMPORT_BLOCK, 1)

    tree_after = ast.parse(updated)
    remaining = {
        node.name
        for node in tree_after.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in TARGETS
    }
    if remaining:
        raise SystemExit(f"Lifecycle definitions unexpectedly remain: {sorted(remaining)}")

    SOURCE.write_text(updated, encoding="utf-8")
    print(f"Extracted {len(TARGETS)} transactional lifecycle helpers")


if __name__ == "__main__":
    main()
