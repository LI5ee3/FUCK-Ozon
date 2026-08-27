#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_PYTHON="$ROOT/.venv/bin/python"

if ! git -C "$ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  printf '错误：不是 Git 项目目录：%s\n' "$ROOT" >&2
  exit 1
fi
printf '项目目录：%s\n' "$ROOT"

git -C "$ROOT" pull --ff-only

if [ ! -x "$VENV_PYTHON" ]; then
  printf '错误：找不到 %s，请先运行 scripts/install-macos.sh。\n' "$VENV_PYTHON" >&2
  exit 1
fi
"$VENV_PYTHON" -m pip install -r "$ROOT/requirements.txt"
"$ROOT/scripts/restart.sh"
curl -fsS --retry 15 --retry-delay 1 --retry-connrefused --max-time 10 \
  http://127.0.0.1:38652/ >/dev/null
printf '%s\n' 'oPanel 更新、重启及本地验证完成。'
