#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "缺少 uv。请先安装：https://docs.astral.sh/uv/"
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "缺少 Node.js/npm，无法安装本地 KaTeX 公式渲染器。"
  exit 1
fi

uv venv --python 3.12 .venv
uv sync --extra dev --quiet
npm install
"$PROJECT_DIR/.venv/bin/cuoti" init

chmod +x "$PROJECT_DIR/打开错题本.command" "$PROJECT_DIR/scripts/setup.sh"
ln -sfn "$PROJECT_DIR/打开错题本.command" "$HOME/Desktop/打开错题本.command"

echo
echo "安装完成。双击桌面的“打开错题本.command”，或运行："
echo "  $PROJECT_DIR/.venv/bin/cuoti serve"
