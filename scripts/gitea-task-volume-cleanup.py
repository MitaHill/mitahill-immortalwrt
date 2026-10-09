#!/usr/bin/env python3
"""Rotate orphaned Gitea task volumes without touching referenced volumes."""
import argparse
import fcntl
import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path


TASK = re.compile(r"^GITEA-ACTIONS-TASK-[0-9]+-.+$")
GIB = 1024 ** 3


def docker(*args):
    result = subprocess.run(
        ["docker", *args], check=True, text=True, capture_output=True, timeout=120
    )
    return result.stdout.strip()


def busy():
    return any(TASK.fullmatch(name) for name in docker("ps", "--format", "{{.Names}}").splitlines())


def rotate(state, dry_run=False, now=None):
    now = time.time() if now is None else now
    if busy():
        print("Build task running; skipping cleanup", flush=True)
        return state
    volumes = []
    for name in docker("volume", "ls", "-q").splitlines():
        if not TASK.fullmatch(name):
            continue
        if docker("ps", "-aq", "--filter", "volume=" + name):
            continue
        info = json.loads(docker("volume", "inspect", name))[0]
        if info["Name"] != name:
            raise ValueError("Volume identity changed")
        created = info["CreatedAt"]
        timestamp = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
        previous = state.get(name, {})
        first_seen = previous.get("first_seen", now) if previous.get("created") == created else now
        volumes.append((timestamp, name, created, first_seen))
    state = {name: {"created": created, "first_seen": first_seen}
             for _, name, created, first_seen in volumes}
    print(f"Unreferenced task volumes: {len(volumes)}", flush=True)
    emergency = shutil.disk_usage("/var/lib/docker").free < 64 * GIB
    for _, name, _, first_seen in sorted(volumes):
        before = shutil.disk_usage("/var/lib/docker").free
        if emergency and before >= 80 * GIB:
            emergency = False
        expired = now - first_seen >= 24 * 3600
        if not expired and not emergency:
            continue
        if busy():
            print("Build task started; stopping cleanup", flush=True)
            break
        if docker("ps", "-aq", "--filter", "volume=" + name):
            state.pop(name, None)
            continue
        reason = "low-space" if emergency else "24-hour-retention"
        print(f"{'Would remove' if dry_run else 'Removing'} {name} reason={reason} free={before}", flush=True)
        if not dry_run:
            docker("volume", "rm", name)
            state.pop(name, None)
            print(f"Removed {name} free={shutil.disk_usage('/var/lib/docker').free}", flush=True)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    directory = Path("/var/lib/gitea-task-volume-cleanup")
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another cleanup is running; skipping")
            return
        path = directory / "state.json"
        state = json.loads(path.read_text()) if path.exists() else {}
        state = rotate(state, args.dry_run)
        if not args.dry_run:
            temporary = directory / "state.json.tmp"
            temporary.write_text(json.dumps(state) + "\n")
            temporary.chmod(0o600)
            temporary.replace(path)


if __name__ == "__main__":
    main()
