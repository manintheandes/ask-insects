#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${ASK_INSECTS_INSTALL_DIR:-$HOME/.local/share/ask-insects/main}"
BIN_DIR="${ASK_INSECTS_BIN_DIR:-$HOME/.local/bin}"
SKILL_DIR="${ASK_INSECTS_SKILL_DIR:-$HOME/.codex/skills/askinsects}"
PYTHON_BIN="${ASK_INSECTS_PYTHON:-$(command -v python3)}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required to install the Ask Insects local runtime" >&2
  exit 127
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$(dirname "$SKILL_DIR")"
rsync -a --delete \
  --exclude='.git/' \
  --exclude='.worktrees/' \
  --exclude='.superpowers/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='._*' \
  --exclude='artifacts/' \
  --exclude='demo-recordings/' \
  --exclude='tmp/' \
  --exclude='.env' \
  "$REPO_ROOT/" "$INSTALL_DIR/"

install -m 0755 "$INSTALL_DIR/scripts/ask-insects-launcher" "$BIN_DIR/ask-insects"
PYTHONPATH="$INSTALL_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" -m askinsects setup-agent --destination "$SKILL_DIR"
