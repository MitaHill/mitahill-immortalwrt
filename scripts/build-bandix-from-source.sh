#!/usr/bin/env bash
set -euo pipefail

target=${1:?target required}
case "$target" in
  x86-64)
    rust_target=x86_64-unknown-linux-musl
    cross_name=x86_64-linux-musl-cross
    cross_cc=x86_64-linux-musl-gcc
    linker_var=CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER
    machine='x86-64'
    ;;
  arm64)
    rust_target=aarch64-unknown-linux-musl
    cross_name=aarch64-linux-musl-cross
    cross_cc=aarch64-linux-musl-gcc
    linker_var=CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER
    machine=AArch64
    ;;
  *) echo "Unsupported target: $target" >&2; exit 2 ;;
esac

recipe=feeds/bandix_backend/openwrt-bandix/Makefile
test -f "$recipe"
version=$(python3 - <<'PY'
from pathlib import Path
import tomllib

data = tomllib.loads(Path("upstream/bandix/bandix/Cargo.toml").read_text())
print(data["package"]["version"])
PY
)
recipe_version=$(sed -n 's/^RUST_BANDIX_VERSION:=//p' "$recipe")
test "$version" = "$recipe_version" || {
  echo "Bandix core $version and package recipe $recipe_version differ" >&2
  exit 1
}

if ! command -v rustup >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs |
    sh -s -- -y --profile minimal --default-toolchain 1.91.1
fi
# shellcheck disable=SC1091
source "$HOME/.cargo/env"
rustup toolchain install 1.91.1
rustup default 1.91.1
rustup target add "$rust_target"
rustup toolchain install nightly --component rust-src
cargo install bpf-linker --version 0.10.2 --locked

cross_dir="$PWD/upstream/musl-cross"
mkdir -p "$cross_dir"
curl --fail --location --retry 3 --silent --show-error \
  "https://github.com/timsaya/musl-cc/releases/download/v0.1.0/${cross_name}.tgz" \
  -o "$cross_dir/${cross_name}.tgz"
tar -xzf "$cross_dir/${cross_name}.tgz" -C "$cross_dir"
linker="$cross_dir/$cross_name/bin/$cross_cc"
test -x "$linker"
export "$linker_var=$linker"

(
  cd upstream/bandix
  cargo build --release --target "$rust_target"
)
binary="upstream/bandix/target/$rust_target/release/bandix"
test -s "$binary"
file "$binary" | grep -Fi "$machine"

archive_name="bandix-${version}-${rust_target}.tar.gz"
archive_root="upstream/bandix-release/bandix-${version}-${rust_target}"
mkdir -p "$archive_root" dl
cp "$binary" "$archive_root/bandix"
cp upstream/bandix/LICENSE upstream/bandix/README.md "$archive_root/"
tar -czf "dl/$archive_name" -C upstream/bandix-release "bandix-${version}-${rust_target}"
hash=$(sha256sum "dl/$archive_name" | cut -d ' ' -f 1)

python3 - "$recipe" "$hash" <<'PY'
from pathlib import Path
import sys

recipe = Path(sys.argv[1])
hash_value = sys.argv[2]
text = recipe.read_text()
marker = "define Package/$(PKG_NAME)\n"
if text.count(marker) != 1:
    raise SystemExit("Cannot locate Bandix package definition")
recipe.write_text(text.replace(marker, f"PKG_HASH:={hash_value}\n\n{marker}", 1))
PY

python3 - "$rust_target" "$hash" <<'PY'
import json
import sys
from pathlib import Path

path = Path("source-revisions.json")
metadata = json.loads(path.read_text())
metadata["bandix_core_build"] = {"rust_target": sys.argv[1], "source_archive_sha256": sys.argv[2]}
path.write_text(json.dumps(metadata, indent=2) + "\n")
PY
