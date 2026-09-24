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

URL="http://127.0.0.1:8765"
if /usr/bin/curl --fail --silent --show-error --max-time 1 "$URL" >/dev/null 2>&1; then
  exec /usr/bin/open "$URL"
fi

if [ "$(uname -s)" = "Darwin" ]; then
  exec "$PROJECT_DIR/.venv/bin/cuoti" service install
fi

exec "$PROJECT_DIR/.venv/bin/cuoti" serve
