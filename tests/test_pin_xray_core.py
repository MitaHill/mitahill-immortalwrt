import runpy
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pin-xray-core.py"
PIN = runpy.run_path(str(SCRIPT))["pin"]


class PinXrayCoreTests(unittest.TestCase):
    def test_updates_version_and_hash_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "Makefile"
            recipe.write_text(
                "PKG_VERSION:=26.9.30\n"
                "PKG_SOURCE_URL:=https://codeload.github.com/XTLS/Xray-core/tar.gz/v$(PKG_VERSION)?\n"
                "PKG_HASH:=old-hash\n"
                "PKG_RELEASE:=1\n"
            )
            PIN(recipe)
            self.assertIn("PKG_VERSION:=26.7.28\n", recipe.read_text())
            self.assertIn("PKG_HASH:=a9afe86349c7bd3e6cae60125e62a5ada09d102e1a2760623e77c24a84dbfb46\n", recipe.read_text())
            self.assertIn("PKG_RELEASE:=1\n", recipe.read_text())

    def test_rejects_a_different_source(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "Makefile"
            content = "PKG_VERSION:=26.9.30\nPKG_SOURCE_URL:=https://example.com/source\nPKG_HASH:=old-hash\n"
            recipe.write_text(content)
            with self.assertRaisesRegex(ValueError, "Unexpected Xray-core source URL"):
                PIN(recipe)
            self.assertEqual(recipe.read_text(), content)


if __name__ == "__main__":
    unittest.main()
