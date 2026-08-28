#!/bin/sh
set -eu

BASE_URL=${1:-http://127.0.0.1:38652}
BASE_URL=${BASE_URL%/}
TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/opanel-frontend-verify.XXXXXX")
trap 'rm -rf "$TEMP_DIR"' EXIT HUP INT TERM

fail() {
  printf '错误：%s\n' "$1" >&2
  exit 1
}

status_for() {
  curl --noproxy '*' -sS --max-time 10 -o "$TEMP_DIR/status-body" -w '%{http_code}' "$BASE_URL$1"
}

ROOT_BODY="$TEMP_DIR/root.html"
ROOT_HEADERS="$TEMP_DIR/root.headers"
if ! curl --noproxy '*' -fsS --retry 15 --retry-delay 1 --retry-connrefused --max-time 10 \
  -D "$ROOT_HEADERS" -o "$ROOT_BODY" "$BASE_URL/"; then
  fail 'production root 未能返回 200。'
fi
grep -Eiq '^content-type:[[:space:]]*text/html' "$ROOT_HEADERS" || fail 'production root 不是 HTML。'
grep -Eiq '^cache-control:[[:space:]]*no-cache' "$ROOT_HEADERS" || fail 'production index 缺少 Cache-Control: no-cache。'
grep -q '<div id="app"></div>' "$ROOT_BODY" || fail 'production root 不是 Vue app shell。'
grep -q '/assets/' "$ROOT_BODY" || fail 'production root 没有引用 Vite assets。'
grep -q '/src/main.ts' "$ROOT_BODY" && fail 'production root 仍引用开发入口 /src/main.ts。'

JS_ASSET=$(sed -n 's/.*src="\([^\"]*\.js\)".*/\1/p' "$ROOT_BODY" | awk '/^\/assets\// { print; exit }')
CSS_ASSET=$(sed -n 's/.*href="\([^\"]*\.css\)".*/\1/p' "$ROOT_BODY" | awk '/^\/assets\// { print; exit }')
[ -n "$JS_ASSET" ] || fail 'production root 没有可验证的 JS asset。'
[ -n "$CSS_ASSET" ] || fail 'production root 没有可验证的 CSS asset。'
curl --noproxy '*' -fsS --max-time 10 -o /dev/null "$BASE_URL$JS_ASSET" || fail 'main JS asset 请求失败。'
curl --noproxy '*' -fsS --max-time 10 -o /dev/null "$BASE_URL$CSS_ASSET" || fail 'main CSS asset 请求失败。'

for route in / /orders /analytics /ads /ads/campaigns /ads/skus /timeliness /risk /returns /alerts /complaints /inventory /profit /transfer /sync /rules /push-subscriptions /dingtalk /settings; do
  if ! status=$(status_for "$route"); then
    fail "deep link $route 请求失败。"
  fi
  [ "$status" = 200 ] || fail "deep link $route 返回 HTTP $status。"
  cmp -s "$ROOT_BODY" "$TEMP_DIR/status-body" || fail "deep link $route 没有返回同一 Vue index。"
done

if ! status=$(status_for /this-route-does-not-exist); then
  fail 'unknown browser route 请求失败。'
fi
[ "$status" = 200 ] || fail "unknown browser route 返回 HTTP $status。"
cmp -s "$ROOT_BODY" "$TEMP_DIR/status-body" || fail 'unknown browser route 没有返回 Vue index。'

for path in /assets/logo.svg /assets/morphicons.js /assets/TABLER_ICONS_LICENSE; do
  if ! status=$(status_for "$path"); then
    fail "current asset $path 请求失败。"
  fi
  [ "$status" = 200 ] || fail "current asset $path 返回 HTTP $status。"
done

for path in /static/logo.svg /static/morphicons.js; do
  if ! status=$(status_for "$path"); then
    fail "legacy asset $path 请求失败。"
  fi
  [ "$status" = 200 ] || fail "legacy asset $path 返回 HTTP $status。"
done

if ! status=$(status_for /assets/does-not-exist.js); then
  fail 'missing Vite asset 请求失败。'
fi
[ "$status" = 404 ] || fail "missing Vite asset 返回 HTTP $status。"
if ! status=$(status_for /static/does-not-exist.js); then
  fail 'missing legacy asset 请求失败。'
fi
[ "$status" = 404 ] || fail "missing legacy asset 返回 HTTP $status。"

SESSION_HEADERS="$TEMP_DIR/session.headers"
SESSION_BODY="$TEMP_DIR/session.json"
if ! status=$(curl --noproxy '*' -sS --max-time 10 -D "$SESSION_HEADERS" -o "$SESSION_BODY" \
  -w '%{http_code}' "$BASE_URL/api/session"); then
  fail '/api/session 请求失败。'
fi
[ "$status" = 200 ] || fail "/api/session 返回 HTTP $status。"
grep -Eiq '^content-type:[[:space:]]*application/json' "$SESSION_HEADERS" || fail '/api/session 不是 JSON。'
grep -q '"authenticated":false' "$SESSION_BODY" || fail '/api/session 未认证契约异常。'

PROTECTED_HEADERS="$TEMP_DIR/protected.headers"
if ! status=$(curl --noproxy '*' -sS --max-time 10 -D "$PROTECTED_HEADERS" -o /dev/null \
  -w '%{http_code}' "$BASE_URL/api/shops"); then
  fail '/api/shops 请求失败。'
fi
[ "$status" = 401 ] || fail "/api/shops 未认证时返回 HTTP $status。"
grep -Eiq '^content-type:[[:space:]]*application/json' "$PROTECTED_HEADERS" || fail '/api/shops 未认证响应不是 JSON。'

if ! status=$(status_for /api/does-not-exist); then
  fail 'unknown API 请求失败。'
fi
[ "$status" = 401 ] || fail "unknown API 未认证时返回 HTTP $status。"

if ! status=$(curl --noproxy '*' -sS --max-time 10 -X POST -o /dev/null -w '%{http_code}' \
  "$BASE_URL/this-route-does-not-exist"); then
  fail 'non-GET unknown route 请求失败。'
fi
case "$status" in
  404|405) ;;
  *) fail "non-GET unknown route 返回 HTTP $status。" ;;
esac

printf 'Vue production serving verification passed：%s\n' "$BASE_URL"
