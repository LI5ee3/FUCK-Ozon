#!/bin/sh
set -eu

touch .env
chmod 600 .env
if ! grep -q '^APP_PORT=' .env; then
  APP_PORT=$(python3 -c 'import secrets,socket
for _ in range(1000):
 p=secrets.randbelow(40001)+20000
 with socket.socket() as s:
  try:s.bind(("0.0.0.0",p))
  except OSError:continue
 print(p);break
else:raise SystemExit("未找到可用端口")')
  printf 'APP_PORT=%s\n' "$APP_PORT" >> .env
fi
if grep -q '^ADMIN_PASSWORD=' .env && ! grep -q '^ADMIN_PASSWORD_HASH=' .env; then
  python3 -c 'from app.security import migrate_env_password; migrate_env_password(".env")'
fi
if ! grep -q '^ADMIN_PASSWORD_HASH=' .env; then
  ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  HASHED=$(python3 -c 'import sys; from app.security import password_hash; print(*password_hash(sys.argv[1]),sep=":")' "$ADMIN_PASSWORD")
  printf 'ADMIN_PASSWORD_SALT=%s\nADMIN_PASSWORD_HASH=%s\n' "$(printf %s "$HASHED" | cut -d: -f1)" "$(printf %s "$HASHED" | cut -d: -f2)" >> .env
  printf '管理员密码 %s\n请立即安全保存密码。\n' "$ADMIN_PASSWORD"
fi

docker compose up -d --build
printf '服务地址：http://服务器IP:%s\n' "$(sed -n 's/^APP_PORT=//p' .env)"
