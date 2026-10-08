#!/usr/bin/env python3
"""Keep Xray-core compatible with the Go version in ImmortalWrt 25.12."""

import re
from pathlib import Path


VERSION = "26.7.28"
SHA256 = "a9afe86349c7bd3e6cae60125e62a5ada09d102e1a2760623e77c24a84dbfb46"
RECIPE = Path("feeds/passwall_packages/xray-core/Makefile")
SOURCE_URL = "PKG_SOURCE_URL:=https://codeload.github.com/XTLS/Xray-core/tar.gz/v$(PKG_VERSION)?"


def pin(recipe: Path) -> None:
    content = recipe.read_text()
    if SOURCE_URL not in content:
        raise ValueError(f"Unexpected Xray-core source URL in {recipe}")
    for key, value in (("PKG_VERSION", VERSION), ("PKG_HASH", SHA256)):
        content, count = re.subn(rf"(?m)^{key}:=.*$", f"{key}:={value}", content)
        if count != 1:
            raise ValueError(f"Expected one {key} assignment in {recipe}, found {count}")
    recipe.write_text(content)


if __name__ == "__main__":
    pin(RECIPE)
    print(f"Pinned Xray-core to {VERSION} for Go 1.26 compatibility")
