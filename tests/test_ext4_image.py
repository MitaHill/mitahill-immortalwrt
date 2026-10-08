import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Ext4ImageTests(unittest.TestCase):
    def run_recipe(self, architecture, fsck_status):
        source = (ROOT / 'include/image.mk').read_text()
        start = source.index('define Image/mkfs/ext4\n')
        end = source.index('\nendef', start) + len('\nendef')
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'bin').mkdir()
            for program in ('make_ext4fs', 'tune2fs', 'e2fsck'):
                script = work / 'bin' / program
                script.write_text(
                    '#!/bin/sh\n'
                    f'echo "{program} $*" >> "$TEST_CALLS"\n'
                    + ('exit "$TEST_FSCK_STATUS"\n' if program == 'e2fsck' else '')
                )
                script.chmod(0o755)
            (work / 'Makefile').write_text(
                f'STAGING_DIR_HOST:={work}\n'
                f'CONFIG_TARGET_x86_64:={"y" if architecture == "x86" else ""}\n'
                'ROOTFS_PARTSIZE:=268435456\nCONFIG_TARGET_EXT4_BLOCKSIZE:=4096\n'
                + source[start:end] + '\nverify:\n\t$(call Image/mkfs/ext4)\n'
            )
            result = subprocess.run(
                ['make', 'verify'], cwd=work, capture_output=True, text=True,
                env=dict(os.environ, TEST_CALLS=str(work / 'calls'),
                         TEST_FSCK_STATUS=str(fsck_status)),
            )
            return result, (work / 'calls').read_text()

    def test_x86_repairs_unmounted_image_and_accepts_corrected_fsck_status(self):
        for status in (0, 1):
            with self.subTest(status=status):
                result, calls = self.run_recipe('x86', status)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('tune2fs -O ^resize_inode verify\n', calls)
                self.assertIn('e2fsck -fy verify\n', calls)

    def test_uncorrectable_filesystem_blocks_image_creation(self):
        result, _ = self.run_recipe('x86', 4)
        self.assertNotEqual(result.returncode, 0)

    def test_arm_image_recipe_is_unchanged(self):
        result, calls = self.run_recipe('arm', 4)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('tune2fs', calls)
        self.assertNotIn('e2fsck', calls)


if __name__ == '__main__':
    unittest.main()
