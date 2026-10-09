#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/retry-download.sh"
shopt -s nullglob

target=${1:?target required}
version=${2:?version required}

case "$target" in
  x86-64)
    config=configs/x86-64.config
    board=x86
    subtarget=64
    target_checks=(CONFIG_TARGET_x86 CONFIG_TARGET_x86_64 CONFIG_TARGET_x86_64_DEVICE_generic)
    ;;
  arm64)
    config=configs/arm64.config
    board=armsr
    subtarget=armv8
    target_checks=(CONFIG_TARGET_armsr CONFIG_TARGET_armsr_armv8 CONFIG_TARGET_armsr_armv8_DEVICE_generic)
    ;;
  *) echo "Unsupported target: $target" >&2; exit 2 ;;
esac

echo "Preparing upstream package sources for $version $target"
bash scripts/prepare-integrated-sources.sh "$target" "$version"
cp "$config" .config
required_packages=(
  luci-app-passwall luci-i18n-passwall-zh-cn
  bandix luci-app-bandix luci-i18n-bandix-zh-cn
  sing-box xray-core geoview chinadns-ng hysteria v2ray-geoip v2ray-geosite
  parted losetup resize2fs blkid lsblk
)
for package in "${required_packages[@]}"; do
  printf 'CONFIG_PACKAGE_%s=y\n' "$package" >> .config
done
# These feeds are build inputs, not repositories hosted by the release mirror.
for feed in bandix_backend bandix_luci passwall_luci passwall_packages video; do
  printf 'CONFIG_FEED_%s=m\n' "$feed" >> .config
done
if [ "$target" = x86-64 ]; then
  mkdir -p files
  cp -a assets/rootfs-expand/. files/
fi
cat >> .config <<'CONFIG'
CONFIG_LUCI_LANG_zh_Hans=y
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_luci-app-passwall_INCLUDE_Geoview=y
CONFIG_PACKAGE_luci-app-passwall_INCLUDE_Hysteria=y
CONFIG_PACKAGE_luci-app-passwall_INCLUDE_V2ray_Geodata=y
CONFIG
make defconfig
for name in "${target_checks[@]}" "${required_packages[@]/#/CONFIG_PACKAGE_}"; do
  grep -qx "${name}=y" .config || {
    echo "Configuration did not select $name" >&2
    exit 1
  }
done
for feed in bandix_backend bandix_luci passwall_luci passwall_packages video; do
  grep -qx "CONFIG_FEED_${feed}=m" .config || {
    echo "Unpublished feed is enabled: $feed" >&2
    exit 1
  }
done

echo "Compiling Bandix core for $target from upstream source"
bash scripts/build-bandix-from-source.sh "$target"
echo "Downloading ImmortalWrt build inputs"
retry_download make download -j10
echo "Building ImmortalWrt $version $target with PassWall and Bandix"
make -j10 V=s

image_dir="bin/targets/$board/$subtarget"
images=("$image_dir"/*-ext4-combined-efi.img.gz)
manifests=("$image_dir"/*.manifest)
test "${#images[@]}" -gt 0
test "${#manifests[@]}" -gt 0
(
  cd "$image_dir"
  sha256sum -c sha256sums
)

bundle="bin/integrated-$target"
mkdir -p "$bundle"
cp "${images[0]}" "$bundle/immortalwrt-$version-$target-passwall-bandix-ext4-combined-efi.img.gz"
cp "${manifests[0]}" "$bundle/immortalwrt-$version-$target-passwall-bandix.manifest"
cp source-revisions.json "$bundle/"
manifest="$bundle/immortalwrt-$version-$target-passwall-bandix.manifest"

for package in "${required_packages[@]}"; do
  grep -Eq "^${package}[[:space:]]" "$manifest" || {
    echo "Firmware manifest is missing $package" >&2
    exit 1
  }
done

for package in \
  luci-app-passwall luci-i18n-passwall-zh-cn \
  bandix luci-app-bandix luci-i18n-bandix-zh-cn \
  sing-box xray-core; do
  found=false
  while IFS= read -r -d '' artifact; do
    cp "$artifact" "$bundle/"
    found=true
  done < <(find bin/packages -type f \( -name "${package}_*.ipk" -o -name "${package}-*.apk" \) -print0)
  test "$found" = true || {
    echo "Compiled package is missing: $package" >&2
    exit 1
  }
done

(
  cd "$bundle"
  sha256sum -- *.img.gz *.manifest *.ipk *.apk source-revisions.json > sha256sums
  sha256sum -c sha256sums
)
