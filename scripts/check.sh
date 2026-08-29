#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
  printf '错误：找不到 %s，请先创建项目虚拟环境。\n' "$VENV_PYTHON" >&2
  exit 1
fi

cd "$ROOT"
"$VENV_PYTHON" -m unittest discover -s tests -p 'test_*.py'

cd "$ROOT/frontend"
npm run type-check
npm run test:profit

"$ROOT/scripts/build-frontend.sh"
printf '%s\n' 'oPanel 核心检查通过。'
