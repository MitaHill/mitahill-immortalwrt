import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GitHubReleaseTests(unittest.TestCase):
    def test_release_attaches_only_firmware_and_manifest_with_source_and_checksums(self):
        for target in ('x86-64', 'arm64'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                bundle = work / f'bin/integrated-{target}'
                bundle.mkdir(parents=True)
                image = bundle / 'firmware.img.gz'
                manifest = bundle / 'firmware.manifest'
                image.write_bytes(b'firmware')
                manifest.write_text('base-files - 1\n')
                (bundle / 'extra.apk').write_bytes(b'package')
                (work / 'source-revisions.json').write_text('{"immortalwrt":"fixture-commit"}\n')
                fakebin = work / 'fakebin'
                fakebin.mkdir()
                gh = fakebin / 'gh'
                gh.write_text(
                    '#!/usr/bin/env python3\n'
                    'import json, pathlib, sys\n'
                    'pathlib.Path("gh-args.json").write_text(json.dumps(sys.argv[1:]))\n'
                )
                gh.chmod(0o755)
                workflow = (ROOT / f'.github/workflows/build-25-12-{target}.yml').read_text()
                release = workflow.split('      - name: Publish GitHub prerelease\n', 1)[1]
                script = textwrap.dedent(release.split('        run: |\n', 1)[1])
                result = subprocess.run(
                    ['bash', '-eu', '-c', script], cwd=work, text=True, capture_output=True,
                    env={**os.environ, 'PATH': f"{fakebin}:{os.environ['PATH']}",
                         'RUNNER_TEMP': str(work), 'GITHUB_SHA': 'fixture-head',
                         'GITHUB_RUN_NUMBER': '42'},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads((work / 'gh-args.json').read_text())
                self.assertEqual(args[:3], ['release', 'create', f'v25.12.2-{target}-build.42'])
                self.assertEqual(args[args.index('--target') + 1], 'fixture-head')
                self.assertEqual(args[-2:], [f'bin/integrated-{target}/firmware.img.gz',
                                            f'bin/integrated-{target}/firmware.manifest'])
                notes = (work / 'release-notes.md').read_text()
                self.assertIn('fixture-commit', notes)
                for artifact in (image, manifest):
                    self.assertIn(hashlib.sha256(artifact.read_bytes()).hexdigest(), notes)


if __name__ == '__main__':
    unittest.main()
