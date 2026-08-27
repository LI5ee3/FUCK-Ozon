#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LABEL=com.opanel.app
DOMAIN="gui/$(id -u)"
MAX_WAIT_ATTEMPTS=20

"$ROOT/scripts/stop.sh"

attempt=0
while launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$MAX_WAIT_ATTEMPTS" ]; then
    printf '%s\n' '错误：oPanel LaunchAgent 未能在预期时间内停止。' >&2
    exit 1
  fi
  sleep 0.25
done

"$ROOT/scripts/start.sh"
