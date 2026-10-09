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

## Runner stability and task-volume rotation

The runner keeps its existing version, Docker network and capacity of one.
Enable native `log.job` with `dir: /data/job-logs`, `retention: 168h` and
`max_size: 1GB`. Set `health_check.min_free_disk_space_mb: 65536`.
Back up `/opt/gitea-runner/config.yaml` and restart only after jobs have ended.

Install `scripts/gitea-task-volume-cleanup.py` into `/usr/local/sbin/` and the
units in `assets/runner/` into `/etc/systemd/system/`. Review `--dry-run`, then
use `systemctl daemon-reload` and `systemctl enable --now gitea-task-volume-cleanup.timer`.
The timer checks every 15 minutes, skips running build tasks, and uses an
exclusive flock. Only unreferenced `GITEA-ACTIONS-TASK-<number>-...` volumes are
eligible; stopped-container references also protect a volume.

The first idle scan records an orphan's identity and observation time under
`/var/lib/gitea-task-volume-cleanup/`. Retention starts then, rather than at
volume creation, so a long-running failed job still gets 24 hours for inspection.
Below 64 GiB free, cleanup removes the oldest eligible volumes regardless of
age until 80 GiB is available. Docker errors stop cleanup; deletion is never forced.
Logs, credentials, tool caches and unrelated images are retained.

Network-only source and toolchain downloads retry at most three times, with
5 and 15 second delays. Compilation, verification and publication are not
retried. The final command's exit code is preserved. Full firmware validation
still runs before publication; expansion requires no network at boot.

Run `python3 -m unittest discover -s tests -v`, shell syntax checks and ShellCheck
before publishing. Roll back by disabling the timer and restoring the runner
configuration backup. Deleted temporary volumes cannot be restored.
