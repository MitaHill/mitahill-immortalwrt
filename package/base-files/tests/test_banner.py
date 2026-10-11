import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'files/usr/libexec/mitahill-banner'
FIXTURES = Path(__file__).parent / 'fixtures/banner'


class BannerTests(unittest.TestCase):
    def render(self, missing=False, ipv6_on_wan=False, zero_delta=False):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            proc = work / 'proc'
            shutil.copytree(FIXTURES, proc)
            if missing:
                shutil.rmtree(proc)
                proc.mkdir()
            fakebin = work / 'bin'
            fakebin.mkdir()
            commands = {
                'sleep': '#!/bin/sh\ncp "$MITAHILL_PROC_ROOT/stat-after" "$MITAHILL_PROC_ROOT/stat"\n',
                'df': '#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted\\n/dev/root 262144 88064 174080 34%% /\\n"\n',
                'ubus': '#!/bin/sh\nprintf "%s\\n" "$2"\n',
                'jsonfilter': '''#!/bin/sh
read -r interface
case "$interface:$*" in
    *wan:*ipv4*) echo 203.0.113.24 ;;
    *wan6:*ipv6*) [ "$IPV6_ON_WAN" = 1 ] || echo 2001:db8:1234::2 ;;
    *wan:*ipv6*) [ "$IPV6_ON_WAN" != 1 ] || echo 2001:db8:1234::3 ;;
esac
''',
            }
            if missing:
                commands = {name: '#!/bin/sh\nexit 1\n' for name in commands}
            if zero_delta:
                commands['sleep'] = '#!/bin/sh\nexit 0\n'
            for name, source in commands.items():
                path = fakebin / name
                path.write_text(source)
                path.chmod(0o755)
            result = subprocess.run(
                ['sh', str(SCRIPT)], text=True, capture_output=True,
                env={**os.environ, 'PATH': f"{fakebin}:{os.environ['PATH']}",
                     'MITAHILL_PROC_ROOT': str(proc),
                     'IPV6_ON_WAN': '1' if ipv6_on_wan else '0'},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            return dict(re.split(r'  +', line.strip(), maxsplit=1) for line in result.stdout.splitlines()
                        if line.strip() and not line.strip().startswith('-'))

    def test_status_uses_available_memory_and_cpu_deltas(self):
        output = self.render()
        self.assertEqual(output['Hostname'], 'ImmortalWrt')
        self.assertEqual(output['Uptime'], '3d 12h 26m')
        self.assertEqual(output['CPU usage'], '8%')
        self.assertEqual(output['Memory'], '312 / 1984 MiB (16%)')
        self.assertEqual(output['Writable disk'], '86 / 256 MiB (34%)')
        self.assertEqual(output['Load (1/5/15m)'], '0.12 / 0.08 / 0.05')
        self.assertEqual(output['WAN IPv6'], '2001:db8:1234::2')
        self.assertEqual(output['WAN IPv4'], '203.0.113.24')

    def test_missing_metrics_display_na_without_errors(self):
        output = self.render(missing=True)
        for label in ('Hostname', 'Uptime', 'CPU usage', 'Load (1/5/15m)', 'Memory', 'Writable disk', 'WAN IPv4', 'WAN IPv6'):
            self.assertTrue(output[label].endswith('N/A'), output)

    def test_ipv6_falls_back_to_wan_for_dual_stack_pppoe(self):
        self.assertEqual(self.render(ipv6_on_wan=True)['WAN IPv6'],
                         '2001:db8:1234::3')

    def test_cpu_with_no_new_ticks_displays_na(self):
        self.assertTrue(self.render(zero_delta=True)['CPU usage'].endswith('N/A'))

    def test_noninteractive_shell_does_not_show_status_or_package_hint(self):
        for name in ('10-mitahill-status.sh', 'apk-cheatsheet.sh'):
            result = subprocess.run(['sh', str(ROOT / 'files/etc/profile.d' / name)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout + result.stderr, '')


if __name__ == '__main__':
    unittest.main()
