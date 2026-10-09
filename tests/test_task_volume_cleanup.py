import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cleanup", ROOT / "scripts/gitea-task-volume-cleanup.py")
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)
NAME = "GITEA-ACTIONS-TASK-215-WORKFLOW-firmware"
CREATED = "2026-10-09T00:00:00Z"


class CleanupTests(unittest.TestCase):
    def run_cleanup(self, *, age=0, free=90, active=False, referenced=False, dry=False,
                    race=False, fail=False):
        removed = []
        checks = []

        def docker(*args):
            checks.append(args)
            if fail:
                raise RuntimeError("Docker unavailable")
            if args[:1] == ("ps",) and "--filter" not in args:
                return NAME if active or (race and len(checks) > 1) else "gitea-runner"
            if args[:2] == ("volume", "ls"):
                return NAME + "\nact-toolcache\nother-data"
            if args[:2] == ("volume", "inspect"):
                return json.dumps([{"Name": NAME, "CreatedAt": CREATED}])
            if args[:1] == ("ps",):
                return "stopped-container" if referenced else ""
            if args[:2] == ("volume", "rm"):
                removed.append(args[2])
                return args[2]
            raise AssertionError(args)

        state = {NAME: {"created": CREATED, "first_seen": 100000 - age}}
        with patch.object(cleanup, "docker", side_effect=docker), patch.object(
            cleanup.shutil, "disk_usage", return_value=SimpleNamespace(free=free * cleanup.GIB)
        ):
            result = cleanup.rotate(state, dry_run=dry, now=100000)
        return removed, result

    def test_retains_orphans_for_24_hours(self):
        self.assertEqual(self.run_cleanup(age=86399)[0], [])

    def test_removes_expired_task_only(self):
        self.assertEqual(self.run_cleanup(age=86400)[0], [NAME])

    def test_low_space_overrides_retention(self):
        self.assertEqual(self.run_cleanup(free=63)[0], [NAME])

    def test_running_task_blocks_cleanup(self):
        self.assertEqual(self.run_cleanup(age=90000, active=True)[0], [])

    def test_stopped_container_reference_protects_volume(self):
        self.assertEqual(self.run_cleanup(age=90000, referenced=True)[0], [])

    def test_new_running_task_stops_deletion(self):
        self.assertEqual(self.run_cleanup(age=90000, race=True)[0], [])

    def test_dry_run_does_not_delete(self):
        self.assertEqual(self.run_cleanup(age=90000, dry=True)[0], [])

    def test_docker_failure_stops_cleanup(self):
        with self.assertRaises(RuntimeError):
            self.run_cleanup(age=90000, fail=True)

    def test_low_space_stops_at_80_gib_and_removes_oldest_first(self):
        older = "GITEA-ACTIONS-TASK-1-WORKFLOW-firmware"
        newer = "GITEA-ACTIONS-TASK-2-WORKFLOW-firmware"
        removed = []

        def docker(*args):
            if args[:2] == ("volume", "ls"):
                return newer + "\n" + older
            if args[:2] == ("volume", "inspect"):
                created = "2026-10-08T00:00:00Z" if args[2] == older else CREATED
                return json.dumps([{"Name": args[2], "CreatedAt": created}])
            if args[:2] == ("volume", "rm"):
                removed.append(args[2])
            return ""

        with patch.object(cleanup, "docker", side_effect=docker), patch.object(
            cleanup.shutil, "disk_usage", side_effect=[
                SimpleNamespace(free=n * cleanup.GIB) for n in (40, 40, 82, 82)
            ]
        ):
            state = cleanup.rotate({}, now=100000)
        self.assertEqual(removed, [older])
        self.assertIn(newer, state)

    def test_duplicate_execution_skips_rotation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            cleanup, "Path", return_value=Path(directory)
        ), patch.object(cleanup.fcntl, "flock", side_effect=BlockingIOError), patch.object(
            cleanup, "rotate"
        ) as rotate, patch("sys.argv", ["cleanup"]):
            cleanup.main()
            rotate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
