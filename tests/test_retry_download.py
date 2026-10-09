import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DownloadRetryTests(unittest.TestCase):
    def run_retry(self, successes):
        return subprocess.run(
            ["bash", "-c", 'source scripts/retry-download.sh; '
             'attempt=0; sleep() { echo "delay:$1"; }; '
             'download() { attempt=$((attempt + 1)); echo "attempt:$attempt"; '
             f'if [ "$attempt" -ge {successes} ]; then return 0; fi; return 7; }}; '
             'retry_download download'], cwd=ROOT, text=True, capture_output=True
        )

    def test_success_does_not_retry(self):
        result = self.run_retry(1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["attempt:1"])

    def test_third_attempt_succeeds_with_required_delays(self):
        result = self.run_retry(3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["attempt:1", "delay:5", "attempt:2", "delay:15", "attempt:3"])

    def test_final_failure_preserves_exit_code(self):
        result = self.run_retry(4)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout.count("attempt:"), 3)


if __name__ == "__main__":
    unittest.main()
