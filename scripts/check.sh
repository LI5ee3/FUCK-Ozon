#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

"$ROOT/scripts/test.sh"
"$ROOT/scripts/build-frontend.sh"
printf '%s\n' 'O3Pilot 核心检查通过。'
