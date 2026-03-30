#!/usr/bin/env bash
set -e

BASE="https://raw.githubusercontent.com/clawlabz/claude-token-stats/main"

mkdir -p ~/.claude/scripts ~/.claude/commands

curl -fsSL "$BASE/token-stats.py" -o ~/.claude/scripts/token-stats.py
curl -fsSL "$BASE/token-stats.md" -o ~/.claude/commands/token-stats.md

echo "✓ /token-stats installed. Restart Claude Code and try /token-stats"
