#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_PYTHON="$ROOT/.venv/bin/python"
LABEL=com.opanel.app
DOMAIN="gui/$(id -u)"
MAX_WAIT_ATTEMPTS=20
DIST="$ROOT/frontend/dist"
DIST_PREVIOUS="$ROOT/frontend/dist.previous"
DIST_FAILED="$ROOT/frontend/dist.failed"

wait_for_stopped() {
  attempt=0
  while launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$MAX_WAIT_ATTEMPTS" ]; then
      printf '%s\n' '错误：O3Pilot LaunchAgent 未能在预期时间内停止。' >&2
      return 1
    fi
    sleep 0.25
  done
}

rollback_frontend() {
  printf '%s\n' '新前端验证失败，正在恢复上一份 frontend/dist。' >&2
  "$ROOT/scripts/stop.sh" || true
  wait_for_stopped || return 1
  if [ ! -e "$DIST_PREVIOUS" ]; then
    printf '%s\n' '错误：找不到 frontend/dist.previous，无法回滚前端。' >&2
    return 1
  fi
  rm -rf "$DIST_FAILED"
  if [ -e "$DIST" ]; then
    mv "$DIST" "$DIST_FAILED"
  fi
  mv "$DIST_PREVIOUS" "$DIST"
  "$ROOT/scripts/start.sh"
  "$ROOT/scripts/verify-frontend.sh"
}

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

"$ROOT/scripts/test.sh"
"$ROOT/scripts/build-frontend.sh"

if ! command -v launchctl >/dev/null 2>&1; then
  printf '%s\n' '错误：找不到 launchctl，无法安全更新用户级服务。' >&2
  exit 1
fi
if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  printf '%s\n' '错误：O3Pilot LaunchAgent 当前未运行，拒绝执行 production update。' >&2
  exit 1
fi
if ! curl -fsS --max-time 10 http://127.0.0.1:38652/api/session >/dev/null; then
  printf '%s\n' '错误：固定地址当前未正常响应，拒绝执行 production update。' >&2
  exit 1
fi

if [ ! -f "$ROOT/data/opanel.db" ]; then
  printf '%s\n' '错误：找不到 production SQLite 数据库，拒绝重启。' >&2
  exit 1
fi
if ! "$VENV_PYTHON" - "$ROOT/data/opanel.db" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
try:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM sync_runs WHERE status='running'"
        ).fetchone()[0]
except sqlite3.Error as error:
    print(f"错误：无法只读检查 production 数据库：{error}", file=sys.stderr)
    raise SystemExit(1)

print(f"运行中的同步任务：{count}")
if count:
    print("错误：当前存在运行中的同步任务，拒绝重启，请任务结束后重新执行。", file=sys.stderr)
    raise SystemExit(1)
PY
then
  exit 1
fi

"$ROOT/scripts/stop.sh"
wait_for_stopped
if ! "$ROOT/scripts/activate-frontend.sh"; then
  "$ROOT/scripts/start.sh" || true
  exit 1
fi

if ! "$ROOT/scripts/start.sh"; then
  if ! rollback_frontend; then
    printf '%s\n' '错误：新前端启动失败，且旧前端回滚也失败。' >&2
  fi
  exit 1
fi
if ! "$ROOT/scripts/verify-frontend.sh"; then
  if rollback_frontend; then
    printf '%s\n' '错误：已恢复上一份前端，production update 未完成。' >&2
  else
    printf '%s\n' '错误：前端验证失败，且旧前端回滚失败。' >&2
  fi
  exit 1
fi

rm -rf "$DIST_PREVIOUS"
printf '%s\n' 'O3Pilot 更新、Vue 前端切换、重启及本地验证完成。'
