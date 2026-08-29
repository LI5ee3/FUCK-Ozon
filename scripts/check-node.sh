#!/bin/sh
set -eu

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
  const [major, minor] = process.argv[1].replace(/^v/, "").split(".").map(Number);
  const supported = (major === 22 && minor >= 18) ||
    (major === 24 && minor >= 11) || major >= 25;
  process.exit(supported ? 0 : 1);
' "$NODE_VERSION"; then
  printf '%s\n' '错误：Node.js 版本不兼容；需要 Node.js 22 >=22.18、Node.js 24 >=24.11，或 Node.js >=25。' >&2
  exit 1
fi
