import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'assets/rootfs-expand/usr/libexec/rootfs-expand.sh'


class RootfsExpandTests(unittest.TestCase):
    def run_fixture(self, *, stale=False, already_rebooted=False, fail_resize=False,
                    no_space=False, fail_parted=False, changed_start=False, done=False,
                    unsupported=False):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            state = work / 'state'
            if already_rebooted:
                Path(str(state) + '.reboot').write_text('/dev/vda2 8388608\n')
            if done:
                Path(str(state) + '.done').write_text('/dev/vda2 8388608\n')
            shell = f'''
. "{SCRIPT}"
rootfs_state="{state}"
rootfs_devices() {{
    {'return 1' if unsupported else ':'}
    rootfs_disk=/dev/vda; rootfs_device=/dev/vda2; rootfs_part=2
    rootfs_start=66048; rootfs_disk_size=8388608
    rootfs_size={'8322527' if no_space else '524288'}
}}
rootfs_table_geometry() {{ echo "{'33817088' if changed_start else '33816576'} {'268435456' if fail_parted else '4261133824'}"; }}
rootfs_kernel_size() {{ echo {'524288' if stale else '8322527'}; }}
rootfs_filesystem_size() {{ echo 4200000000; }}
blkid() {{ case "$*" in *PTTYPE*) echo gpt;; *) echo ext4;; esac; }}
parted() {{ echo "parted $*" >> "{work}/calls"; {'return 1' if fail_parted else ':'}; }}
resize2fs() {{ echo "resize2fs $*" >> "{work}/calls"; {'return 1' if fail_resize else ':'}; }}
sync() {{ echo sync >> "{work}/calls"; }}
reboot() {{ echo reboot >> "{work}/calls"; }}
rootfs_expand
'''
            result = subprocess.run(['sh', '-c', shell], text=True, capture_output=True,
                                    env=dict(os.environ, http_proxy='http://127.0.0.1:1',
                                             https_proxy='http://127.0.0.1:1'))
            calls = (work / 'calls').read_text() if (work / 'calls').exists() else ''
            return result, calls, Path(str(state) + '.done').exists(), Path(str(state) + '.reboot').exists()

    def test_expands_offline_without_reboot_when_kernel_updates(self):
        result, calls, done, _ = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('parted ---pretend-input-tty /dev/vda resizepart 2 100%', calls)
        self.assertIn('resize2fs /dev/vda2', calls)
        self.assertNotIn('reboot', calls)
        self.assertTrue(done)

    def test_stale_kernel_reboots_once_before_resizing(self):
        result, calls, done, pending = self.run_fixture(stale=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls.count('reboot'), 1)
        self.assertNotIn('resize2fs', calls)
        self.assertFalse(done)
        self.assertTrue(pending)

    def test_stale_kernel_after_reboot_does_not_loop(self):
        result, calls, done, _ = self.run_fixture(stale=True, already_rebooted=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('reboot', calls)
        self.assertFalse(done)

    def test_resume_after_reboot_finishes_without_another_reboot(self):
        result, calls, done, pending = self.run_fixture(no_space=True, already_rebooted=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('parted', calls)
        self.assertNotIn('reboot', calls)
        self.assertTrue(done)
        self.assertFalse(pending)

    def test_failed_partition_resize_never_resizes_filesystem(self):
        result, calls, done, _ = self.run_fixture(fail_parted=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('resize2fs', calls)
        self.assertFalse(done)

    def test_changed_partition_start_is_rejected(self):
        result, calls, done, _ = self.run_fixture(changed_start=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('resize2fs', calls)
        self.assertFalse(done)

    def test_failed_filesystem_resize_does_not_mark_done(self):
        result, calls, done, _ = self.run_fixture(fail_resize=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(done)
        self.assertNotIn('reboot', calls)

    def test_completed_disk_and_unsupported_root_do_no_work(self):
        for fixture in ({'done': True}, {'unsupported': True}):
            with self.subTest(fixture=fixture):
                result, calls, _, _ = self.run_fixture(**fixture)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(calls, '')


if __name__ == '__main__':
    unittest.main()
