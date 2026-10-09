import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    "luci-app-passwall",
    "luci-i18n-passwall-zh-cn",
    "bandix",
    "luci-app-bandix",
    "luci-i18n-bandix-zh-cn",
    "sing-box",
    "xray-core",
    "geoview", "chinadns-ng", "hysteria", "v2ray-geoip", "v2ray-geosite",
    "parted", "losetup", "resize2fs", "blkid", "lsblk",
)


class IntegratedBuildTests(unittest.TestCase):
    def run_fixture(self, target, version, extension, missing_package=None, dropped_config=None):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / "scripts").mkdir()
            (work / "configs").mkdir()
            (work / "fakebin").mkdir()
            shutil.copytree(ROOT / "assets", work / "assets", symlinks=True)
            shutil.copy(ROOT / "scripts/run-integrated-build.sh", work / "scripts")
            shutil.copy(ROOT / "scripts/retry-download.sh", work / "scripts")
            shutil.copy(ROOT / f"configs/{target}.config", work / "configs")
            (work / "scripts/prepare-integrated-sources.sh").write_text(
                '#!/bin/sh\nprintf "{}\\n" > source-revisions.json\n'
            )
            (work / "scripts/build-bandix-from-source.sh").write_text("#!/bin/sh\n")
            (work / "fakebin/make").write_text(
                "#!/usr/bin/env python3\n"
                "import hashlib, os, pathlib, sys\n"
                "if 'defconfig' in sys.argv:\n"
                "    config = pathlib.Path('.config')\n"
                "    dropped = os.environ.get('TEST_DROPPED_CONFIG')\n"
                "    if dropped: config.write_text(config.read_text().replace(dropped + '=y', '# ' + dropped + ' is not set'))\n"
                "    sys.exit(0)\n"
                "if 'download' in sys.argv: sys.exit(0)\n"
                "root = pathlib.Path('bin')\n"
                "target = os.environ['TEST_TARGET']\n"
                "board, sub = ('x86', '64') if target == 'x86-64' else ('armsr', 'armv8')\n"
                "output = root / 'targets' / board / sub\n"
                "output.mkdir(parents=True)\n"
                "image = output / 'firmware-ext4-combined-efi.img.gz'\n"
                "image.write_bytes(b'firmware')\n"
                "manifest = output / 'firmware.manifest'\n"
                "manifest.write_text(''.join(p + ' - 1\\n' for p in os.environ['TEST_PACKAGES'].split(',')))\n"
                "checksums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\\n' for p in (image, manifest))\n"
                "(output / 'sha256sums').write_text(checksums)\n"
                "packages = root / 'packages' / 'test'\n"
                "packages.mkdir(parents=True)\n"
                "for package in os.environ['TEST_PACKAGES'].split(','):\n"
                "    suffix = '_1.ipk' if os.environ['TEST_EXTENSION'] == 'ipk' else '-1.apk'\n"
                "    (packages / (package + suffix)).write_bytes(package.encode())\n"
            )
            (work / "fakebin/make").chmod(0o755)
            env = dict(os.environ)
            env.update(
                PATH=f"{work / 'fakebin'}:{env['PATH']}",
                TEST_TARGET=target,
                TEST_EXTENSION=extension,
                TEST_PACKAGES=",".join(p for p in PACKAGES if p != missing_package),
                TEST_DROPPED_CONFIG=dropped_config or "",
            )
            result = subprocess.run(
                ["bash", "scripts/run-integrated-build.sh", target, version],
                cwd=work,
                env=env,
                text=True,
                capture_output=True,
            )
            if missing_package or dropped_config:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(missing_package or dropped_config, result.stderr)
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = (work / ".config").read_text()
            for feed in ("bandix_backend", "bandix_luci", "passwall_luci", "passwall_packages", "video"):
                self.assertIn(f"CONFIG_FEED_{feed}=m\n", config)
            if target == "x86-64":
                self.assertTrue((work / "files/etc/rc.d/S12rootfs-expand").is_symlink())
                self.assertTrue((work / "files/usr/libexec/rootfs-expand.sh").exists())
            else:
                self.assertFalse((work / "files").exists())
            bundle = work / "bin" / f"integrated-{target}"
            self.assertTrue((bundle / f"immortalwrt-{version}-{target}-passwall-bandix-ext4-combined-efi.img.gz").exists())
            self.assertTrue((bundle / "source-revisions.json").exists())
            self.assertEqual(len(list(bundle.glob(f"*.{extension}"))), 7)
            for line in (bundle / "sha256sums").read_text().splitlines():
                digest, name = line.split(maxsplit=1)
                self.assertEqual(hashlib.sha256((bundle / name).read_bytes()).hexdigest(), digest)

    def test_missing_dependency_blocks_release(self):
        for package in PACKAGES:
            with self.subTest(package=package):
                self.run_fixture("x86-64", "25.12.2", "apk", missing_package=package)

    def test_unselected_dependency_blocks_build(self):
        self.run_fixture("x86-64", "25.12.2", "apk", dropped_config="CONFIG_PACKAGE_hysteria")

    def test_x86_ipk_firmware_contains_selected_packages(self):
        self.run_fixture("x86-64", "24.10.5", "ipk")

    def test_arm64_apk_firmware_contains_selected_packages(self):
        self.run_fixture("arm64", "25.12.2", "apk")


if __name__ == "__main__":
    unittest.main()
