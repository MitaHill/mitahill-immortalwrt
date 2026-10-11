# GitHub 固件构建

`25.12` 分支完整保留 ImmortalWrt 官方 `v25.12.2` 源码，并提供
`build-25-12-x86-64.yml` 与 `build-25-12-arm64.yml`。使用 GitHub Actions 手动在 Linux x86-64
runner 上构建 `x86/64` 或 `armsr/armv8` 固件。推送不会自动构建，
每次通过 GitHub CLI 选择一个目标。两个工作流均使用 `make -j10`。

构建时从上游 `main` 拉取 PassWall 的 LuCI 与依赖包、Bandix 核心、
OpenWrt 包配方及 LuCI 应用。PassWall 和 Bandix 的 OpenWrt 包由本次
ImmortalWrt 构建系统编译。Bandix 核心先用 Rust 1.91.1、`bpf-linker` 和
所选架构的 musl 工具链从源码编译，再由 Bandix 包配方封装并选入固件。
构建要求 Bandix 核心版本与包配方版本一致。

每次运行的 `source-revisions.json` 记录 ImmortalWrt 与五个上游仓库的
commit，以及 Bandix 源码构建包的 SHA256。`bin/integrated-<target>/` 包含
EFI 镜像、manifest、已编译的 PassWall/Bandix 软件包、版本记录和
`sha256sums`。工作流先核对目标输出的校验文件，再核对定制目录中的
校验文件与 manifest，最后将这些内容上传为 GitHub artifact 和预发布版附件。

两个目标都使用 `ubuntu-24.04` Linux runner；ARM64 是固件目标架构，
不依赖 Mac M5 runner。25.12 使用 APK 软件包。构建期间的软件包和
上游源码只保存在该次运行的工作目录，完成后由发布附件保留产物与来源记录。

## 内置依赖与离线扩容

构建显式选入 Geoview、ChinaDNS-NG、Hysteria、V2Ray GeoIP/GeoSite，
以及 parted、losetup、resize2fs、blkid、lsblk。配置与 manifest 缺少任一
必需包都会使构建失败。未发布的定制 feed 和 video 的镜像站地址默认注释，
不影响从这些 feed 编译并内置软件包。

x86-64 ext4 镜像生成后，在构建机上清除 make_ext4fs 的 resize_inode
特性并运行 e2fsck，避免已有保留 GDT 布局导致在线扩容失败。这一步
发生在打包前、文件系统未挂载时，不增加设备启动步骤。

x86-64 ext4 镜像在启动阶段自动识别根分区、修复 GPT 尾部位置并扩容。
工具和脚本全部内置，不下载内容、不等待网络、不安装软件。
只有内核仍看到旧分区容量时才自动重启一次；随后在线扩展实际 ext4
文件系统，不创建额外 loop 映射，不进行第二次重启。其他文件系统、
非第二分区或根分区之后还有分区的布局会跳过。日志位于
`/tmp/rootfs-expand.log`；成功状态记录于 `/etc/rootfs-expand.done`。

本地逻辑检查：`python3 -m unittest discover -s tests -v`。
x86 工作流在发布前使用断网 QEMU 验证实际包清单、4 GiB 磁盘扩容、
再次启动及原始大小磁盘；任何验证失败均不发布固件。ARM64 不安装
自动扩容脚本，未进行 ARM64 启动验证。

## GitHub CLI

```sh
gh workflow run build-25-12-x86-64.yml --repo MitaHill/mitahill-immortalwrt --ref 25.12
gh run list --repo MitaHill/mitahill-immortalwrt --workflow build-25-12-x86-64.yml --limit 5
gh run watch <run-id> --repo MitaHill/mitahill-immortalwrt --exit-status
```

ARM64 使用 `build-25-12-arm64.yml`。工作流通过 GitHub 自带的临时 token
发布预发布版，无需配置 Gitea 或单独的发布凭据。Artifact 保留七天，
Release 只附加定制 EFI 镜像与 manifest；来源记录和 SHA256 写入发布说明。
软件包、校验和文件及来源记录保存在 Actions artifact。

下载失败最多重试三次，间隔 5 秒和 15 秒；编译、验证和发布失败不自动重试。
GitHub 托管 runner 每次运行独立，不使用原 Gitea 的任务卷轮换服务。

## SSH welcome banner

保留 ImmortalWrt Logo，增加 MitaHill 标识及全英文状态摘要：Hostname、
Uptime、CPU usage、Load (1/5/15m)、Memory、Writable disk、WAN IPv4/IPv6。
缺失指标显示 `N/A`。CPU 使用率通过 0.2 秒的累计计数差计算；内存使用
`MemTotal - MemAvailable`；磁盘优先取 `/overlay`，否则取 `/`。
WAN 地址来自本机 ubus 接口状态，IPv6 优先取 wan6，随后取 wan；不查询外部服务。
只在交互式登录显示动态摘要和简短 APK 提示，failsafe 保持原有提示。

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s package/base-files/tests -v
```

运行 shell 语法检查和 ShellCheck；完整固件编译及 AMD64 断网启动验证在
GitHub Actions 中执行。ARM64 未进行启动验证。
