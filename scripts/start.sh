#!/bin/sh
set -eu

LABEL=com.opanel.app
USER_HOME=$(printenv HOME)
DOMAIN="gui/$(id -u)"
PLIST="$USER_HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$PLIST" ]; then
  printf '错误：找不到 %s，请先运行 scripts/install-macos.sh。\n' "$PLIST" >&2
  exit 1
fi

if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootstrap "$DOMAIN" "$PLIST"
fi
launchctl kickstart -k "$DOMAIN/$LABEL"
printf '%s\n' 'O3Pilot launchd 服务已启动。'
