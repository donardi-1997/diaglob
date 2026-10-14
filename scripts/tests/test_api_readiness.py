"""No-network CI contract tests for the production API readiness gate."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-api-readiness.sh"
GOOD = '{"status":"ok","service":"diaglob-api","database":"connected","multitenant":true,"multistore":true}'


class ReadinessGateTests(unittest.TestCase):
    def run_gate(self, responses, *, attempts=3, interval=0, **overrides):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "counter"
            fake_curl = Path(tmp) / "curl"
            fake_curl.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, sys\n"
                "state = pathlib.Path(os.environ['FAKE_CURL_COUNT'])\n"
                "count = int(state.read_text()) if state.exists() else 0\n"
                "state.write_text(str(count + 1))\n"
                "rows = json.loads(os.environ['FAKE_CURL_RESPONSES'])\n"
                "status, body = rows[min(count, len(rows)-1)]\n"
                "if status != 0: sys.exit(status)\n"
                "sys.stdout.write(body)\n"
            )
            fake_curl.chmod(0o755)
            env = dict(
                os.environ,
                PATH=tmp + os.pathsep + os.environ["PATH"],
                FAKE_CURL_COUNT=str(state),
                FAKE_CURL_RESPONSES=json.dumps(responses),
                DIAGLOB_HEALTH_URL="https://api.diaglob.tech/health",
                DIAGLOB_READINESS_REQUIRE_SERVICE="0",
                DIAGLOB_HEALTH_ATTEMPTS=str(attempts),
                DIAGLOB_HEALTH_INTERVAL=str(interval),
            )
            env.update(overrides)
            result = subprocess.run(
                ["bash", str(SCRIPT)], env=env, text=True,
                capture_output=True, timeout=20, check=False,
            )
            return result, int(state.read_text()) if state.exists() else 0

    def test_waits_for_startup_and_recovers_from_502(self):
        result, calls = self.run_gate([(22, ""), (0, GOOD)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, 2)
        self.assertIn("attempt 2/3", result.stdout)

    def test_db_disconnected_is_not_ready(self):
        result, calls = self.run_gate(
            [(0, GOOD.replace('"connected"', '"disconnected"'))], attempts=2,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, 2)

    def test_rejects_bad_json_and_missing_fields(self):
        result, calls = self.run_gate([(0, "not JSON"), (0, "{}")], attempts=2)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, 2)

    def test_rejects_wrong_app_and_disabled_multitenancy(self):
        for body in (
            GOOD.replace('"diaglob-api"', '"other"'),
            GOOD.replace('"multitenant":true', '"multitenant":false'),
        ):
            result, _ = self.run_gate([(0, body)], attempts=1)
            self.assertEqual(result.returncode, 1)

    def test_rejects_unapproved_target_before_network(self):
        result, calls = self.run_gate(
            [(0, GOOD)], DIAGLOB_HEALTH_URL="https://unknown.example/health",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, 0)

    def test_rejects_unbounded_wait(self):
        result, calls = self.run_gate([(0, GOOD)], attempts=600)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
