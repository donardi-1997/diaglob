"""Prevents accidental exposure of Telegram recipient metadata in CI logs."""
from pathlib import Path
import copy
import json
import subprocess
import sys

import yaml


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


def _workflow_audit_validator():
    """Extract the exact Python check that Actions runs; no replica logic."""
    source = (ROOT / WORKFLOWS[0]).read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    steps = workflow["jobs"]["read-only-sla"]["steps"]
    run = next(x["run"] for x in steps if x.get("id") == "audit")
    start = "python3 -c '\n"
    end = "\n' \"$remote_status\")\""
    assert run.count(start) == 1
    assert run.count(end) == 1
    return run.split(start, 1)[1].split(end, 1)[0]


def _synthetic_watch_report(*, attention):
    return {
        "audit": "shopify_privacy_sla_watch_read_only",
        "state": "critical" if attention else "normal",
        "attention_required": attention,
        "read_only": True,
        "privacy_release_ready": False,
        "fulfillment_authorized": False,
        "fulfillment_complete": False,
        "receipt_total": 1,
        "counts": {
            "tenant_store_unresolved": 1 if attention else 0,
            "review_api_unavailable_with_open_receipts": 1 if attention else 0,
        },
    }


def _validate_audit_json(report, exit_code):
    return subprocess.run(
        [sys.executable, "-c", _workflow_audit_validator(), str(exit_code)],
        input=json.dumps(report) if not isinstance(report, str) else report,
        capture_output=True, text=True, check=False,
    )


def test_privacy_alert_exit2_is_a_successfully_parsed_actionable_exception():
    result = _validate_audit_json(_synthetic_watch_report(attention=True), 2)
    assert result.returncode == 0
    assert result.stdout.strip() == "critical 1 1 1 1"


def test_privacy_healthy_exit0_is_a_successfully_parsed_heartbeat():
    result = _validate_audit_json(_synthetic_watch_report(attention=False), 0)
    assert result.returncode == 0
    assert result.stdout.strip() == "normal 0 1 0 0"


def test_watch_parser_rejects_failed_audits_and_false_green_states():
    critical = _synthetic_watch_report(attention=True)
    assert _validate_audit_json(critical, 0).returncode != 0
    assert _validate_audit_json(critical, 1).returncode != 0

    for key, value in (
        ("privacy_release_ready", True),
        ("fulfillment_complete", True),
        ("fulfillment_authorized", True),
        ("read_only", False),
        ("state", "normal"),
        ("attention_required", "true"),
    ):
        forged = dict(critical)
        forged[key] = value
        assert _validate_audit_json(forged, 2).returncode != 0

    bad_counts = dict(critical)
    bad_counts["counts"] = {"tenant_store_unresolved": "secret@example.com"}
    assert _validate_audit_json(bad_counts, 2).returncode != 0
    assert _validate_audit_json("not valid json", 2).returncode != 0


def test_watch_requires_successful_notification_for_pending_privacy_issue():
    source = (ROOT / WORKFLOWS[0]).read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    steps = workflow["jobs"]["read-only-sla"]["steps"]
    audit = next(x for x in steps if x.get("id") == "audit")
    notify = next(x for x in steps if "sendMessage" in x.get("run", ""))
    assert "remote_status" in audit["run"]
    assert "PRIVACY_WATCH_TECHNICAL_FAILURE" in audit["run"]
    assert "PRIVACY_WATCH_REPORT_INVALID" in audit["run"]
    assert "steps.audit.outputs.attention == '1'" in notify["if"]
    assert "failure()" in notify["if"]
    assert "PRIVACY_ALERT_DELIVERY_UNAVAILABLE" in notify["run"]
    assert "exit 1" in notify["run"]
    assert "curl --fail" in notify["run"]
    assert "continue-on-error" not in source
    # An alert cannot claim the underlying Shopify request was fulfilled.
    assert "NOT GDPR completion" in notify["run"]
    assert "issues/266" in notify["run"]
