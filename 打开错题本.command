#!/usr/bin/env bash
set -euo pipefail

SOURCE="$0"
while [ -L "$SOURCE" ]; do
  LINK_DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" = /* ]] || SOURCE="$LINK_DIR/$SOURCE"
done
PROJECT_DIR="$(cd "$(dirname "$SOURCE")" && pwd)"

if [ ! -x "$PROJECT_DIR/.venv/bin/cuoti" ]; then
  "$PROJECT_DIR/scripts/setup.sh"
fi

exec "$PROJECT_DIR/.venv/bin/cuoti" serve
