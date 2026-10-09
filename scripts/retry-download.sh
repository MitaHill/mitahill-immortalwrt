#!/usr/bin/env bash
# Source this helper for network-only operations; never retry compilation.
retry_download() {
  local delay status
  for delay in 5 15; do
    if "$@"; then
      return 0
    else
      status=$?
    fi
    printf 'Download failed (exit %s); retrying in %ss\n' "$status" "$delay" >&2
    sleep "$delay"
  done
  "$@"
}
