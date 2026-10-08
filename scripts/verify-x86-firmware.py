#!/usr/bin/env python3
"""Boot the release image without a network before allowing publication."""
import argparse
import gzip
import os
import selectors
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

REQUIRED_PACKAGES = (
    'luci-app-passwall', 'luci-i18n-passwall-zh-cn', 'bandix', 'luci-app-bandix',
    'luci-i18n-bandix-zh-cn', 'sing-box', 'xray-core', 'geoview', 'chinadns-ng',
    'hysteria', 'v2ray-geoip', 'v2ray-geosite', 'parted', 'losetup', 'resize2fs',
    'blkid', 'lsblk',
)


def boot_and_verify(disk, minimum_kib, allow_reboot):
    firmware = Path('/usr/share/OVMF/OVMF_CODE.fd')
    command = [
        'qemu-system-x86_64', '-machine', 'q35', '-m', '1024',
        '-drive', f'if=pflash,format=raw,readonly=on,file={firmware}',
        '-drive', f'file={disk},format=raw,if=virtio',
        '-nographic', '-net', 'none', '-no-reboot',
    ]
    checks = f'''
ok=1
waited=0
while ! test -s /etc/rootfs-expand.done && test "$waited" -lt 90; do
    sleep 1
    waited=$((waited + 1))
done
for p in {' '.join(REQUIRED_PACKAGES)}; do
    apk info -e "$p" >/dev/null || {{ echo "Missing package: $p"; ok=0; }}
done
test -s /etc/rootfs-expand.done || ok=0
size=$(df -Pk / | awk 'NR==2 {{print $2}}')
test "$size" -ge {minimum_kib} || ok=0
if grep -h -v '^[[:space:]]*#' /etc/apk/repositories.d/*.list | grep -E '/(bandix_backend|bandix_luci|passwall_luci|passwall_packages|video)/packages.adb'; then ok=0; fi
cat /tmp/rootfs-expand.log
if test "$ok" = 1; then printf '\\nFW_VERIFY:%s\\n' PASS; else printf '\\nFW_VERIFY:%s\\n' FAIL; fi
poweroff
'''
    payload = "cat > /tmp/fw-verify.sh <<'FW_EOF'\n" + checks + "\nFW_EOF\nsh /tmp/fw-verify.sh\n"
    for attempt in range(2 if allow_reboot else 1):
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, bufsize=0) as process:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            transcript = b''
            sent = False
            deadline = time.monotonic() + 240
            next_enter = time.monotonic()
            try:
                while time.monotonic() < deadline:
                    for key, _ in selector.select(timeout=1):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if chunk:
                            transcript += chunk
                            print(chunk.decode(errors='replace'), end='', flush=True)
                    if process.poll() is not None:
                        break
                    if not sent and time.monotonic() >= next_enter:
                        process.stdin.write(b'\n')
                        next_enter = time.monotonic() + 2
                    if not sent and b'root@' in transcript and b':~#' in transcript:
                        # Keep each terminal line short and let the emulated UART drain.
                        data = payload.encode()
                        for offset in range(0, len(data), 64):
                            chunk = memoryview(data[offset:offset + 64])
                            while chunk:
                                chunk = chunk[process.stdin.write(chunk):]
                            time.sleep(0.02)
                        sent = True
                    if b'FW_VERIFY:FAIL' in transcript:
                        raise RuntimeError('Offline firmware verification failed')
                    if b'FW_VERIFY:PASS' in transcript:
                        process.wait(timeout=30)
                        print(f'\nOffline verification passed (automatic reboots: {attempt})')
                        return
                if b'reboot: Restarting system' not in transcript or attempt != 0 or not allow_reboot:
                    raise RuntimeError('Guest failed to verify within the boot/reboot budget')
            finally:
                selector.close()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    raise RuntimeError('Firmware exceeded one automatic reboot')


def verify(image):
    with tempfile.TemporaryDirectory(prefix='firmware-offline-') as directory:
        disk = Path(directory) / 'firmware.img'
        with gzip.open(image, 'rb') as source, disk.open('wb') as target:
            shutil.copyfileobj(source, target)
        original_size = disk.stat().st_size
        with disk.open('r+b') as target:
            target.truncate(4 * 1024**3)
        boot_and_verify(disk, 3 * 1024**2, allow_reboot=True)
        # Completion must survive a cold boot without another resize or reboot.
        boot_and_verify(disk, 3 * 1024**2, allow_reboot=False)
        with gzip.open(image, 'rb') as source, disk.open('wb') as target:
            shutil.copyfileobj(source, target)
        assert disk.stat().st_size == original_size
        boot_and_verify(disk, 100 * 1024, allow_reboot=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    verify(parser.parse_args().image)
