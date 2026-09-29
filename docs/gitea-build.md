# Gitea 固件构建

`25.12` 分支完整保留 ImmortalWrt 官方 `v25.12.2` 源码，并提供
`build-25-12-x86-64.yml` 与 `build-25-12-arm64.yml`。推送本分支会分别在 Linux x86-64
runner 上构建 `x86/64` 和 `armsr/armv8` 固件；也可以在 Gitea Actions 中
单独手动运行一个目标。两个工作流均使用 `make -j10`。

构建时从上游 `main` 拉取 PassWall 的 LuCI 与依赖包、Bandix 核心、
OpenWrt 包配方及 LuCI 应用。PassWall 和 Bandix 的 OpenWrt 包由本次
ImmortalWrt 构建系统编译。Bandix 核心先用 Rust 1.91.1、`bpf-linker` 和
所选架构的 musl 工具链从源码编译，再由 Bandix 包配方封装并选入固件。
构建要求 Bandix 核心版本与包配方版本一致。

每次运行的 `source-revisions.json` 记录 ImmortalWrt 与五个上游仓库的
commit，以及 Bandix 源码构建包的 SHA256。`bin/integrated-<target>/` 包含
EFI 镜像、manifest、已编译的 PassWall/Bandix 软件包、版本记录和
`sha256sums`。工作流先核对目标输出的校验文件，再核对定制目录中的
校验文件与 manifest，最后将这些内容上传为 Gitea artifact 和预发布版附件。

两个目标都使用 `ubuntu-latest` Linux runner；ARM64 是固件目标架构，
不依赖 Mac M5 runner。25.12 使用 APK 软件包。构建期间的软件包和
上游源码只保存在该次运行的工作目录，完成后由发布附件保留产物与来源记录。
