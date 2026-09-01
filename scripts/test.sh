#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$ROOT/.venv/bin/python"

"$ROOT/scripts/check-node.sh"

if [ ! -x "$PYTHON" ]; then
  PYTHON=$(command -v python3 || command -v python || true)
fi
if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  printf '%s\n' '错误：需要 Python 3.12 或更高版本。' >&2
  exit 1
fi

cd "$ROOT/frontend"
npm ci

cd "$ROOT"
"$PYTHON" -m unittest discover -s tests -p 'test_*.py'

cd "$ROOT/frontend"
npm run type-check
npm run test:unit
npm run test:shipping

printf '%s\n' 'O3Pilot 测试与类型检查通过。'
