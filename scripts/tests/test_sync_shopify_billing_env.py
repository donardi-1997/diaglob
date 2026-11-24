"""Contract tests for scripts/sync_shopify_billing_env.py (no network)."""
import importlib.util
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "sync_shopify_billing_env.py"
spec = importlib.util.spec_from_file_location("sync_shopify_billing_env", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

HANDLES = {
    "starter": {"plan": "starter", "prices": {"EVERY_30_DAYS": "19.00", "ANNUAL": "190.00"}},
    "growth": {"plan": "growth", "prices": {"EVERY_30_DAYS": "49.00", "ANNUAL": "490.00"}},
    "pro": {"plan": "pro", "prices": {"EVERY_30_DAYS": "99.00", "ANNUAL": "990.00"}},
}
FULL = {
    "SHOPIFY_PARTNER_ORG_ID": "5148778",
    "SHOPIFY_PARTNER_APP_GID": "gid://shopify/App/416524435457",
    "SHOPIFY_PARTNER_ACCESS_TOKEN": "prtapi_" + "a" * 32,
    "SHOPIFY_APP_PRICING_HANDLES_JSON": json.dumps(HANDLES),
    "SHOPIFY_APP_STORE_HANDLE": "diaglob",
    "SHOPIFY_BILLING_ENTITLEMENTS_ENABLED": "true",
    "SHOPIFY_BILLING_SCHEDULER_ENABLED": "true",
}


class SyncShopifyBillingEnvTests(unittest.TestCase):
    def run_script(self, env_text, payload):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "diaglob.env"
            env.write_text(env_text, encoding="utf-8")
            data = Path(tmp) / "payload.json"
            data.write_text(json.dumps(payload), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(env), str(data)],
                capture_output=True, text=True,
            )
            return proc, env.read_text(encoding="utf-8"), data.exists()

    def test_writes_all_keys_and_never_prints_values(self):
        proc, text, payload_left = self.run_script("FOO=bar\nSHOPIFY_BILLING_ENTITLEMENTS_ENABLED=false\n", FULL)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(payload_left)
        self.assertIn("FOO=bar\n", text)
        self.assertIn("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED=true\n", text)
        self.assertEqual(text.count("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED="), 1)
        self.assertNotIn(FULL["SHOPIFY_PARTNER_ACCESS_TOKEN"], proc.stdout + proc.stderr)
        self.assertNotIn("5148778", proc.stdout)

    def test_json_survives_bash_sourcing(self):
        proc, text, _ = self.run_script("", FULL)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        line = next(l for l in text.splitlines() if l.startswith("SHOPIFY_APP_PRICING_HANDLES_JSON="))
        value = line.split("=", 1)[1]
        self.assertEqual(json.loads(shlex.split(value)[0]), HANDLES)

    def test_idempotent(self):
        _, first, _ = self.run_script("", FULL)
        proc, second, _ = self.run_script(first, FULL)
        self.assertEqual(first, second)
        self.assertNotIn(" CHANGED:", proc.stdout)
        self.assertIn("UNCHANGED: SHOPIFY_PARTNER_ACCESS_TOKEN", proc.stdout)

    def test_empty_values_do_not_wipe_existing(self):
        proc, text, _ = self.run_script("SHOPIFY_APP_STORE_HANDLE=diaglob\n", {"SHOPIFY_APP_STORE_HANDLE": ""})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("SHOPIFY_BILLING_SYNC_SKIPPED", proc.stdout)
        self.assertEqual(text, "SHOPIFY_APP_STORE_HANDLE=diaglob\n")

    def test_invalid_value_leaves_file_untouched(self):
        for key, bad in [
            ("SHOPIFY_PARTNER_APP_GID", "gid://partners/App/1"),
            ("SHOPIFY_PARTNER_ACCESS_TOKEN", "short"),
            ("SHOPIFY_PARTNER_ACCESS_TOKEN", "x" * 30 + "\nEVIL=1"),
            ("SHOPIFY_APP_PRICING_HANDLES_JSON", json.dumps({"starter": {"plan": "scale"}})),
            ("SHOPIFY_APP_PRICING_HANDLES_JSON", "{'a': 1}"),
            ("SHOPIFY_APP_STORE_HANDLE", "Diaglob App"),
            ("SHOPIFY_BILLING_SCHEDULER_ENABLED", "yes"),
        ]:
            with self.subTest(key=key, bad=bad):
                payload = dict(FULL, **{key: bad})
                proc, text, payload_left = self.run_script("FOO=bar\n", payload)
                self.assertEqual(proc.returncode, 1)
                self.assertEqual(text, "FOO=bar\n")
                self.assertIn(key, proc.stderr)
                self.assertFalse(payload_left)

    def test_validate_payload_formats_json(self):
        out = sync.validate_payload(FULL)
        self.assertTrue(out["SHOPIFY_APP_PRICING_HANDLES_JSON"].startswith("'{"))
        self.assertNotIn(" ", out["SHOPIFY_APP_PRICING_HANDLES_JSON"])


if __name__ == "__main__":
    unittest.main()
