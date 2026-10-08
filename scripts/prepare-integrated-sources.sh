#!/usr/bin/env bash
set -euo pipefail

target=${1:?target required}
version=${2:?version required}

case "$target" in
  x86-64|arm64) ;;
  *) echo "Unsupported target: $target" >&2; exit 2 ;;
esac

mkdir -p upstream
{
  printf '%s\n' \
    'src-git passwall_packages https://github.com/Openwrt-Passwall/openwrt-passwall-packages.git;main' \
    'src-git passwall_luci https://github.com/Openwrt-Passwall/openwrt-passwall.git;main' \
    'src-git bandix_backend https://github.com/timsaya/openwrt-bandix.git;main' \
    'src-git bandix_luci https://github.com/timsaya/luci-app-bandix.git;main'
  cat feeds.conf.default
} > feeds.conf

./scripts/feeds update -a
python3 scripts/pin-xray-core.py
./scripts/feeds install -a -f -p passwall_packages
./scripts/feeds install -a -f -p passwall_luci
./scripts/feeds install -a
git clone --depth=1 https://github.com/timsaya/bandix.git upstream/bandix

for source_path in \
  package/feeds/passwall_luci/luci-app-passwall \
  package/feeds/passwall_packages/xray-core \
  package/feeds/passwall_packages/sing-box \
  package/feeds/bandix_backend/openwrt-bandix \
  package/feeds/bandix_luci/luci-app-bandix; do
  test -e "$source_path" || {
    echo "Missing source package: $source_path" >&2
    exit 1
  }
done

python3 - "$target" "$version" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

target, version = sys.argv[1:]
repositories = {
    "immortalwrt": ".",
    "passwall_packages": "feeds/passwall_packages",
    "passwall_luci": "feeds/passwall_luci",
    "bandix_backend": "feeds/bandix_backend",
    "bandix_luci": "feeds/bandix_luci",
    "bandix_core": "upstream/bandix",
}
revisions = {
    name: subprocess.check_output(
        ["git", "-C", path, "rev-parse", "HEAD"], text=True
    ).strip()
    for name, path in repositories.items()
}
Path("source-revisions.json").write_text(
    json.dumps(
        {
            "version": version,
            "target": target,
            "revisions": revisions,
            "xray_core_override": {
                "version": "26.7.28",
                "source_sha256": "a9afe86349c7bd3e6cae60125e62a5ada09d102e1a2760623e77c24a84dbfb46",
            },
        },
        indent=2,
    )
    + "\n"
)
PY
