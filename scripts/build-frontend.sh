#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FRONTEND="$ROOT/frontend"
STAGING="$FRONTEND/dist.next"

"$ROOT/scripts/check-node.sh"

if [ ! -f "$FRONTEND/package.json" ] || [ ! -f "$FRONTEND/package-lock.json" ]; then
  printf '%s\n' '错误：frontend/package.json 或 package-lock.json 不存在。' >&2
  exit 1
fi

rm -rf "$STAGING"
cd "$FRONTEND"
npm run build -- --outDir dist.next

if [ ! -f "$STAGING/index.html" ]; then
  printf '%s\n' '错误：Vue production build 缺少 dist.next/index.html。' >&2
  exit 1
fi
if [ ! -d "$STAGING/assets" ]; then
  printf '%s\n' '错误：Vue production build 缺少 dist.next/assets。' >&2
  exit 1
fi
JS_ASSET=$(find "$STAGING/assets" -type f -name '*.js' -print -quit)
CSS_ASSET=$(find "$STAGING/assets" -type f -name '*.css' -print -quit)
if [ -z "$JS_ASSET" ] || [ -z "$CSS_ASSET" ]; then
  printf '%s\n' '错误：Vue production build 至少需要一个 JS 和一个 CSS asset。' >&2
  exit 1
fi
for source in "$FRONTEND/public/assets"/*; do
  [ -f "$source" ] || continue
  asset=${source##*/}
  if [ ! -f "$STAGING/assets/$asset" ]; then
    printf '错误：Vue production build 缺少 assets/%s。\n' "$asset" >&2
    exit 1
  fi
  if ! cmp -s "$source" "$STAGING/assets/$asset"; then
    printf '错误：构建后的 assets/%s 与 frontend/public/assets/%s 不一致。\n' "$asset" "$asset" >&2
    exit 1
  fi
done
if ! grep -q '/assets/' "$STAGING/index.html"; then
  printf '%s\n' '错误：构建后的 index.html 没有引用 /assets/。' >&2
  exit 1
fi
if grep -q '/src/main.ts' "$STAGING/index.html"; then
  printf '%s\n' '错误：构建后的 index.html 仍引用开发入口 /src/main.ts。' >&2
  exit 1
fi
if grep -R -n '/static/' "$STAGING/index.html" "$STAGING/assets" >/dev/null 2>&1; then
  printf '%s\n' '错误：Vue production build 仍包含 /static/ runtime 引用。' >&2
  grep -R -n '/static/' "$STAGING/index.html" "$STAGING/assets" >&2
  exit 1
fi

printf 'Staged Vue build ready：%s\n' "$STAGING"
printf 'JS asset：%s\nCSS asset：%s\n' "$JS_ASSET" "$CSS_ASSET"
