#!/bin/sh
set -eu

LABEL=com.opanel.app
DOMAIN="gui/$(id -u)"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL"
  printf '%s\n' 'O3Pilot launchd 服务已停止并卸载。'
else
  printf '%s\n' 'O3Pilot launchd 服务当前未加载。'
fi
