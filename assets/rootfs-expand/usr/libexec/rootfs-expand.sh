#!/bin/sh
# shellcheck shell=ash
# SPDX-License-Identifier: GPL-2.0-only
# Only the ext4 root of the x86 combined image is supported.

rootfs_state=/etc/rootfs-expand

rootfs_devices() {
    local device_id block sibling start size
    device_id=$(awk '$5 == "/" { for (i=6; i<=NF; i++) if ($i == "-" && $(i+1) == "ext4") print $3 }' /proc/self/mountinfo)
    [ -n "$device_id" ] || return 1
    block=$(readlink -f "/sys/dev/block/$device_id")
    [ -f "$block/partition" ] || return 1
    rootfs_block=$block
    rootfs_disk_block=${block%/*}
    rootfs_part=$(cat "$block/partition")
    rootfs_device="/dev/${block##*/}"
    rootfs_disk="/dev/${rootfs_disk_block##*/}"
    rootfs_start=$(cat "$block/start")
    rootfs_size=$(cat "$block/size")
    rootfs_disk_size=$(cat "$rootfs_disk_block/size")
    [ "$rootfs_part" = 2 ] || return 1
    # The BIOS boot partition may have a higher number but a lower start.
    for sibling in "$rootfs_disk_block"/*; do
        [ -f "$sibling/partition" ] || continue
        start=$(cat "$sibling/start")
        size=$(cat "$sibling/size")
        [ "$start" -gt "$rootfs_start" ] && [ "$size" -gt 0 ] && return 1
    done
    return 0
}

rootfs_table_geometry() {
    parted -m -s -f "$rootfs_disk" unit B print |
        awk -F: -v part="$rootfs_part" '$1 == part { gsub(/B/, "", $2); gsub(/B/, "", $4); print $2, $4 }'
}

rootfs_kernel_size() {
    cat "$rootfs_block/size"
}

rootfs_filesystem_size() {
    df -Pk / | awk 'NR == 2 { printf "%.0f\n", $2 * 1024 }'
}

rootfs_expand() {
    local signature tool geometry table_start table_size kernel_size filesystem_size
    rootfs_devices || { echo 'Skipping unsupported root or partition layout'; return 0; }
    signature="$rootfs_device $rootfs_disk_size"
    [ -f "$rootfs_state.done" ] && [ "$(cat "$rootfs_state.done")" = "$signature" ] && return 0
    for tool in parted resize2fs blkid; do
        command -v "$tool" >/dev/null || { echo "Missing built-in tool: $tool"; return 1; }
    done
    [ "$(blkid -p -s TYPE -o value "$rootfs_device")" = ext4 ] || return 1
    case "$(blkid -p -s PTTYPE -o value "$rootfs_disk")" in
        gpt|dos) ;;
        *) echo 'Unsupported partition table'; return 1 ;;
    esac

    # Ignore the GPT trailer and alignment gap; only grow when space is useful.
    if [ $((rootfs_disk_size - rootfs_start - rootfs_size)) -gt 2048 ]; then
        echo "Growing $rootfs_device on $rootfs_disk"
        # Repair the backup GPT in script mode first. A mounted partition also
        # needs a Yes answer, which --script refuses even with --fix.
        # Parted may report a kernel reread failure after successfully writing.
        rootfs_table_geometry >/dev/null || return 1
        printf 'Yes\n' | parted ---pretend-input-tty "$rootfs_disk" resizepart "$rootfs_part" 100% ||
            echo 'Parted reported an error; checking the on-disk table'
    fi
    geometry=$(rootfs_table_geometry) || return 1
    # Geometry deliberately splits into start and size.
    # shellcheck disable=SC2086
    set -- $geometry
    [ "$#" = 2 ] || { echo 'Cannot read partition geometry'; return 1; }
    table_start=$1
    table_size=$2
    [ "$table_start" -eq $((rootfs_start * 512)) ] || { echo 'Partition start changed'; return 1; }
    [ "$table_size" -ge $((rootfs_size * 512)) ] || { echo 'Partition unexpectedly shrank'; return 1; }
    [ $((rootfs_disk_size * 512 - table_start - table_size)) -le 1048576 ] || {
        echo 'Partition did not expand to the end of the disk'; return 1;
    }
    kernel_size=$(rootfs_kernel_size) || return 1
    if [ $((kernel_size * 512)) -lt "$table_size" ]; then
        [ -f "$rootfs_state.reboot" ] && [ "$(cat "$rootfs_state.reboot")" = "$signature" ] && {
            echo 'Partition capacity still stale after reboot; refusing a reboot loop'; return 1;
        }
        printf '%s\n' "$signature" > "$rootfs_state.reboot" || return 1
        sync
        echo 'Rebooting once to refresh the root partition capacity'
        reboot
        return 0
    fi
    # resize2fs itself skips an already full filesystem, including small growth.
    resize2fs "$rootfs_device" || return 1
    filesystem_size=$(rootfs_filesystem_size) || return 1
    [ "$filesystem_size" -ge $((table_size * 9 / 10)) ] || {
        echo 'Filesystem capacity did not grow'; return 1;
    }
    printf '%s\n' "$signature" > "$rootfs_state.done" || return 1
    rm -f "$rootfs_state.reboot"
    echo "Expansion complete: $filesystem_size bytes usable filesystem capacity"
}
