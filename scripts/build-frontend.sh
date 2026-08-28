#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FRONTEND="$ROOT/frontend"
STAGING="$FRONTEND/dist.next"

if ! command -v node >/dev/null 2>&1; then
  printf '%s\n' '错误：找不到 Node.js，请安装受支持的 Node.js 后重试。' >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  printf '%s\n' '错误：找不到 npm，请安装受支持的 npm 后重试。' >&2
  exit 1
fi

NODE_VERSION=$(node --version)
NPM_VERSION=$(npm --version)
printf 'Node.js：%s\n' "$NODE_VERSION"
printf 'npm：%s\n' "$NPM_VERSION"
# ponytail: lockfile-derived engine floor; update when dependency engines change.
if ! node -e '
  const [major, minor] = process.versions.node.split(".").map(Number);
  const supported = (major === 22 && minor >= 18) ||
    (major === 24 && minor >= 11) || major >= 25;
  process.exit(supported ? 0 : 1);
'; then
  printf '%s\n' '错误：Node.js 版本不兼容；frontend/package-lock.json 要求 Node.js 22.18.x 或 >=24.11.0。' >&2
  exit 1
fi
if [ ! -f "$FRONTEND/package.json" ] || [ ! -f "$FRONTEND/package-lock.json" ]; then
  printf '%s\n' '错误：frontend/package.json 或 package-lock.json 不存在。' >&2
  exit 1
fi

rm -rf "$STAGING"
cd "$FRONTEND"
npm ci
npm run type-check
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
for asset in logo.svg morphicons.js TABLER_ICONS_LICENSE; do
  if [ ! -f "$STAGING/assets/$asset" ]; then
    printf '错误：Vue production build 缺少 assets/%s。\n' "$asset" >&2
    exit 1
  fi
  if ! cmp -s "$FRONTEND/public/assets/$asset" "$STAGING/assets/$asset"; then
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
