#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
FIXED_PORT=38652
ENV_FILE="$ROOT/.env"
VENV="$ROOT/.venv"
VENV_PYTHON="$VENV/bin/python"
PLIST_TEMPLATE="$ROOT/deploy/com.opanel.app.plist"
LABEL=com.opanel.app

if [ "$(uname -s)" != "Darwin" ]; then
  printf '%s\n' '错误：O3Pilot 的生产部署脚本只支持 macOS。' >&2
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  printf '%s\n' '错误：请使用普通用户运行，不要使用 sudo。' >&2
  exit 1
fi

if ! command -v lsof >/dev/null 2>&1; then
  printf '%s\n' '错误：找不到 lsof，无法检查固定端口。' >&2
  exit 1
fi

if ! command -v launchctl >/dev/null 2>&1; then
  printf '%s\n' '错误：找不到 launchctl，无法安装用户级服务。' >&2
  exit 1
fi

if ! command -v plutil >/dev/null 2>&1; then
  printf '%s\n' '错误：找不到 plutil，无法校验 launchd 配置。' >&2
  exit 1
fi

if PORT_INFO=$(lsof -nP -iTCP:"$FIXED_PORT" -sTCP:LISTEN 2>/dev/null); then
  printf '错误：固定端口 %s 已被占用：\n%s\n' "$FIXED_PORT" "$PORT_INFO" >&2
  exit 1
fi

PYTHON=
for candidate in python3.14 python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' >/dev/null 2>&1
  then
    PYTHON=$(command -v "$candidate")
    break
  fi
done

if [ -z "$PYTHON" ]; then
  printf '%s\n' '错误：需要 Python 3.12 或更高版本，优先使用 python3.14。' >&2
  exit 1
fi

printf '使用 Python：%s\n' "$("$PYTHON" --version 2>&1)"

venv_is_valid() {
  [ -x "$VENV_PYTHON" ] || return 1
  "$VENV_PYTHON" - "$VENV" <<'PY'
from pathlib import Path
import os
import sys

expected = Path(os.path.realpath(sys.argv[1]))
prefix = Path(os.path.realpath(sys.prefix))
executable = Path(os.path.abspath(sys.executable))
executable_env = Path(os.path.realpath(os.path.dirname(os.path.dirname(executable))))

if sys.version_info < (3, 12):
    raise SystemExit(1)

if sys.prefix == sys.base_prefix or prefix != expected or executable_env != expected:
    raise SystemExit(1)

try:
    config_lines = (expected / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeError):
    raise SystemExit(1)

command = None
for line in config_lines:
    key, separator, value = line.partition("=")
    if separator and key.strip() == "command":
        command = value.strip()
        break

if command is None:
    raise SystemExit(1)

_, separator, recorded_path = command.partition(" -m venv ")
if not separator or Path(os.path.realpath(recorded_path)) != expected:
    raise SystemExit(1)
PY
}

if [ -e "$VENV" ] || [ -L "$VENV" ]; then
  if ! venv_is_valid; then
    printf '%s\n' '检测到虚拟环境路径已失效或项目目录发生变化，正在重建 .venv。'
    rm -rf "$VENV"
  fi
fi

if [ ! -d "$VENV" ]; then
  "$PYTHON" -m venv "$VENV"
fi

if ! venv_is_valid; then
  printf '%s\n' '错误：.venv 创建后验证失败，拒绝继续安装。' >&2
  exit 1
fi

"$VENV_PYTHON" -m pip install -r "$ROOT/requirements.txt"
if [ -e "$VENV/bin/uvicorn" ] || [ -L "$VENV/bin/uvicorn" ]; then
  if ! "$VENV/bin/uvicorn" --version >/dev/null 2>&1; then
    printf '%s\n' '错误：uvicorn console script 验证失败，拒绝继续安装。' >&2
    exit 1
  fi
fi
"$ROOT/scripts/test.sh"
"$ROOT/scripts/build-frontend.sh"

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

if grep -q '^ADMIN_PASSWORD=' "$ENV_FILE" &&
  ! grep -Eq '^ADMIN_PASSWORD_HASH=.+$' "$ENV_FILE"
then
  "$VENV_PYTHON" -c 'from app.security import migrate_env_password; migrate_env_password(".env")'
fi

if ! grep -Eq '^ADMIN_PASSWORD_HASH=.+$' "$ENV_FILE"; then
  ADMIN_PASSWORD=$("$VENV_PYTHON" -c 'import secrets; print(secrets.token_urlsafe(18))')
  HASHED=$(printf '%s' "$ADMIN_PASSWORD" |
    "$VENV_PYTHON" -c 'import sys; from app.security import password_hash; print(":".join(password_hash(sys.stdin.read())))')
  ADMIN_PASSWORD_SALT=$(printf '%s\n' "$HASHED" | cut -d: -f1)
  ADMIN_PASSWORD_HASH=$(printf '%s\n' "$HASHED" | cut -d: -f2)
  printf 'ADMIN_PASSWORD_SALT=%s\nADMIN_PASSWORD_HASH=%s\n' \
    "$ADMIN_PASSWORD_SALT" "$ADMIN_PASSWORD_HASH" >> "$ENV_FILE"
  printf '管理员初始密码：%s\n请立即安全保存，此密码只显示一次。\n' "$ADMIN_PASSWORD"
fi

chmod 600 "$ENV_FILE"

if ! USER_HOME=$(printenv HOME); then
  printf '%s\n' '错误：HOME 未设置，无法安装用户级 launchd 服务。' >&2
  exit 1
fi
PLIST_DIR="$USER_HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/$LABEL.plist"
mkdir -p "$ROOT/logs" "$PLIST_DIR"

"$VENV_PYTHON" - "$PLIST_TEMPLATE" "$PLIST" "$ROOT" <<'PY'
from pathlib import Path
from xml.sax.saxutils import escape
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
root = escape(sys.argv[3])
rendered = template.replace("__OPANEL_ROOT__", root)
if "__OPANEL_ROOT__" in rendered:
    raise SystemExit("launchd 模板渲染失败")
Path(sys.argv[2]).write_text(rendered, encoding="utf-8")
PY

plutil -lint "$PLIST"
"$ROOT/scripts/activate-frontend.sh"
if ! "$ROOT/scripts/start.sh"; then
  "$ROOT/scripts/stop.sh" || true
  printf '%s\n' '错误：O3Pilot launchd 服务未能启动，安装已停止。' >&2
  exit 1
fi
if ! "$ROOT/scripts/verify-frontend.sh"; then
  "$ROOT/scripts/stop.sh" || true
  printf '%s\n' '错误：O3Pilot Vue production 前端验证失败，安装已停止。' >&2
  exit 1
fi
rm -rf "$ROOT/frontend/dist.previous"
printf '%s\n' 'O3Pilot 已启动并通过 http://127.0.0.1:38652/ 验证。'
