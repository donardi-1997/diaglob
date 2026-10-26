"""Shopify configuration changes must not silently skip source validation."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_shopify_config_changes_trigger_backend_and_frontend_validation():
    workflow = yaml.safe_load((ROOT / ".github/workflows/validate-pr.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["changes"]["steps"]
    detection = next(step["run"] for step in steps if step.get("id") == "scope")
    branch = detection.split("shopify.app.toml|shopify/*)", 1)
    assert len(branch) == 2, "Shopify source changes are missing from scope detection"
    assignments = branch[1].split(";;", 1)[0]
    assert "backend=true" in assignments
    assert "frontend=true" in assignments


def test_backend_validation_runs_read_only_shopify_source_preflight():
    workflow = yaml.safe_load((ROOT / ".github/workflows/validate-pr.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["backend"]["steps"]
    gate = next((step for step in steps if step.get("name") == "Shopify review source preflight"), None)
    assert gate is not None
    assert gate["working-directory"] == "backend"
    assert "python -m tools.shopify_review_source_preflight --config ../shopify.app.toml" in gate["run"]
    assert "continue-on-error" not in gate
    assert "|| true" not in gate["run"]
    assert "deploy" not in gate["run"]


def test_production_deployment_requires_shopify_source_validation():
    workflow = yaml.safe_load((ROOT / ".github/workflows/deploy-production.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert jobs["deploy"]["needs"] == "validate"
    gate = next((step for step in jobs["validate"]["steps"]
                 if step.get("name") == "Shopify review source preflight"), None)
    assert gate is not None
    assert gate["working-directory"] == "backend"
    assert gate["run"] == "python -m tools.shopify_review_source_preflight --config ../shopify.app.toml"
    assert "if" not in gate
    assert "continue-on-error" not in gate
    assert "continue-on-error" not in jobs["validate"]
