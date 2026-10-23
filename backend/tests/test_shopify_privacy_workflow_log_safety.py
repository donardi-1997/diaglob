"""Prevents accidental exposure of Telegram recipient metadata in CI logs."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/shopify-privacy-sla-watch.yml",
    ".github/workflows/shopify-billing-hourly.yml",
    ".github/workflows/deploy-production.yml",
)


def test_alert_workflows_hide_telegram_api_response_bodies():
    for relative_path in WORKFLOWS:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "/sendMessage" in source, relative_path
        # Telegram's JSON response contains the recipient's name, chat ID
        # and username, none of which should be copied into Actions logs.
        assert "curl --fail --silent --show-error --output /dev/null" in source, (
            relative_path
        )


def test_privacy_watch_starts_after_successful_main_deploy_not_parallel_push():
    source = (ROOT / WORKFLOWS[0]).read_text(encoding="utf-8")
    assert "workflow_run:" in source
    assert 'workflows: ["Deploy Production"]' in source
    assert "workflow_run.conclusion == 'success'" in source
    assert "workflow_run.head_branch == 'main'" in source
    assert "schedule:" in source
    assert "workflow_dispatch:" in source
