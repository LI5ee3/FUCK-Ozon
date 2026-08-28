#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DIST="$ROOT/frontend/dist"
DIST_NEXT="$ROOT/frontend/dist.next"
DIST_PREVIOUS="$ROOT/frontend/dist.previous"

if [ ! -f "$DIST_NEXT/index.html" ]; then
  printf '%s\n' '错误：找不到 staged frontend/dist.next/index.html，拒绝切换。' >&2
  exit 1
fi

rm -rf "$DIST_PREVIOUS"
if [ -e "$DIST" ]; then
  mv "$DIST" "$DIST_PREVIOUS"
fi
if ! mv "$DIST_NEXT" "$DIST"; then
  if [ ! -e "$DIST" ] && [ -e "$DIST_PREVIOUS" ]; then
    mv "$DIST_PREVIOUS" "$DIST"
  fi
  printf '%s\n' '错误：无法激活 staged frontend/dist。' >&2
  exit 1
fi
printf '%s\n' '已激活 staged frontend/dist。'
