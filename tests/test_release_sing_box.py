import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(ROOT / "scripts/use-release-sing-box.py"))
SELECT = SCRIPT["select_asset"]
CONFIGURE = SCRIPT["configure"]


def release():
    return {
        "tag_name": "v1.14.3", "draft": False, "prerelease": False,
        "assets": [
            {
                "name": f"sing-box-1.14.3-linux-{arch}-musl.tar.gz",
                "digest": "sha256:" + ("a" if arch == "amd64" else "b") * 64,
                "browser_download_url": f"https://github.com/SagerNet/sing-box/releases/download/v1.14.3/sing-box-1.14.3-linux-{arch}-musl.tar.gz",
            }
            for arch in ("amd64", "arm64")
        ],
    }


class ReleaseSingBoxTests(unittest.TestCase):
    def test_stable_release_generates_matching_package_and_source_record(self):
        for target, arch in (("x86-64", "amd64"), ("arm64", "arm64")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                recipe, record = work / "Makefile", work / "source-revisions.json"
                record.write_text('{"revisions":{"immortalwrt":"fixture"}}\n')
                asset = CONFIGURE(release(), target, recipe, record)
                content = recipe.read_text()
                self.assertIn("PKG_VERSION:=1.14.3\n", content)
                self.assertIn(f"linux-{arch}-musl.tar.gz", content)
                self.assertIn("PKG_HASH:=" + asset["sha256"], content)
                self.assertIn("define Build/Compile\nendef", content)
                self.assertNotIn("golang", content)
                self.assertNotIn("tiny", content)
                metadata = json.loads(record.read_text())
                self.assertEqual(metadata["sing_box_release"], asset)
                self.assertEqual(metadata["revisions"]["immortalwrt"], "fixture")

    def test_invalid_release_or_asset_does_not_change_files(self):
        variants = []
        for field in ("draft", "prerelease"):
            data = release()
            data[field] = True
            variants.append(data)
        data = release()
        data["tag_name"] = "v1.15.0-alpha.1"
        variants.append(data)
        for field, value in (("digest", None), ("digest", "sha256:bad"),
                             ("browser_download_url", "https://example.com/binary")):
            data = release()
            data["assets"][0][field] = value
            variants.append(data)
        data = release()
        data["assets"] = data["assets"][1:]
        variants.append(data)
        data = release()
        data["assets"].append(copy.deepcopy(data["assets"][0]))
        variants.append(data)
        for data in variants:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                recipe, record = Path(directory) / "Makefile", Path(directory) / "record.json"
                recipe.write_text("existing recipe\n")
                record.write_text('{}\n')
                with self.assertRaises(ValueError):
                    CONFIGURE(data, "x86-64", recipe, record)
                self.assertEqual(recipe.read_text(), "existing recipe\n")
                self.assertEqual(record.read_text(), '{}\n')

    def test_openwrt_download_rule_rejects_corrupted_archive(self):
        asset = SELECT(release(), "x86-64")
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / asset["asset"]
            archive.write_bytes(b"corrupted archive")
            mkhash = Path(directory) / "mkhash"
            mkhash.write_text(
                '#!/usr/bin/env python3\nimport hashlib, pathlib, sys\n'
                'data = pathlib.Path(sys.argv[2]).read_bytes() if len(sys.argv) > 2 else sys.stdin.buffer.read()\n'
                'print(hashlib.sha256(data).hexdigest())\n'
            )
            mkhash.chmod(0o755)
            result = subprocess.run(
                ["perl", str(ROOT / "scripts/download.pl"), directory, asset["asset"],
                 asset["sha256"], asset["asset"], "file://" + directory],
                capture_output=True, text=True, timeout=20,
                env={**os.environ, "MKHASH": str(mkhash), "TOPDIR": str(ROOT)},
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("does not match", result.stderr)


if __name__ == "__main__":
    unittest.main()
