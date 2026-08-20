#!/bin/sh
set -eu

touch .env
chmod 600 .env
if ! grep -q '^APP_PORT=' .env; then
  APP_PORT=$(python3 -c 'import secrets; print(secrets.randbelow(40001)+20000)')
  printf 'APP_PORT=%s\n' "$APP_PORT" >> .env
fi
if ! grep -q '^ADMIN_PASSWORD=' .env; then
  ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  printf 'ADMIN_PASSWORD=%s\n' "$ADMIN_PASSWORD" >> .env
  printf '管理员密码 %s\n请立即安全保存密码。\n' "$ADMIN_PASSWORD"
fi

docker compose up -d --build
printf '服务地址：http://服务器IP:%s\n' "$(sed -n 's/^APP_PORT=//p' .env)"
