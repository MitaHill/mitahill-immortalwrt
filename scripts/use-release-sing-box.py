#!/usr/bin/env python3
"""Package the latest stable SagerNet musl binary instead of compiling sing-box."""

import json
from pathlib import Path
import re
import subprocess
import sys


RECIPE = Path("feeds/passwall_packages/sing-box/Makefile")
SOURCE_RECORD = Path("source-revisions.json")
ARCHITECTURES = {"x86-64": "amd64", "arm64": "arm64"}


def select_asset(release, target):
    arch = ARCHITECTURES[target]
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)", release["tag_name"])
    if release.get("draft") or release.get("prerelease") or not match:
        raise ValueError("Expected a stable sing-box release")
    version = match.group(1)
    filename = f"sing-box-{version}-linux-{arch}-musl.tar.gz"
    assets = [asset for asset in release["assets"] if asset["name"] == filename]
    if len(assets) != 1:
        raise ValueError(f"Expected one release asset: {filename}")
    asset = assets[0]
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(f"Missing SHA256 for {filename}")
    url = asset["browser_download_url"]
    expected_url = f"https://github.com/SagerNet/sing-box/releases/download/v{version}/{filename}"
    if url != expected_url:
        raise ValueError(f"Unexpected release URL: {url}")
    return {
        "version": version,
        "architecture": arch,
        "asset": filename,
        "url": url,
        "sha256": digest.removeprefix("sha256:"),
        "source": "SagerNet GitHub stable release (precompiled musl)",
    }


def package_recipe(asset):
    version, arch = asset["version"], asset["architecture"]
    return f"""# SPDX-License-Identifier: GPL-3.0-only
# Official full musl release; no Go or Cronet compilation in this package.
include $(TOPDIR)/rules.mk

PKG_NAME:=sing-box
PKG_VERSION:={version}
PKG_RELEASE:=1
PKG_SOURCE:={asset['asset']}
PKG_SOURCE_URL:={asset['url'].rsplit('/', 1)[0]}/
PKG_HASH:={asset['sha256']}
PKG_BUILD_DIR:=$(BUILD_DIR)/sing-box-$(PKG_VERSION)-linux-{arch}-musl
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=LICENSE

include $(INCLUDE_DIR)/package.mk

define Package/sing-box
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=The universal proxy platform
  URL:=https://sing-box.sagernet.org/
  DEPENDS:=@(aarch64||x86_64) +ca-bundle +kmod-inet-diag +kmod-netlink-diag +kmod-tun
  USERID:=sing-box=5566:sing-box=5566
endef

define Build/Compile
endef

define Package/sing-box/install
\t$(INSTALL_DIR) $(1)/usr/bin
\t$(INSTALL_BIN) $(PKG_BUILD_DIR)/sing-box $(1)/usr/bin/sing-box
endef

$(eval $(call BuildPackage,sing-box))
"""


def configure(release, target, recipe=RECIPE, record=SOURCE_RECORD):
    asset = select_asset(release, target)
    metadata = json.loads(record.read_text())
    metadata["sing_box_release"] = asset
    recipe.write_text(package_recipe(asset))
    record.write_text(json.dumps(metadata, indent=2) + "\n")
    return asset


if __name__ == "__main__":
    release = json.loads(subprocess.check_output(
        ["gh", "api", "repos/SagerNet/sing-box/releases/latest"], text=True,
    ))
    asset = configure(release, sys.argv[1])
    print(f"sing-box {asset['version']}: official {asset['architecture']} musl release, SHA256 {asset['sha256']}")
