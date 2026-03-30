# Token Usage Statistics

## Instructions

Run the following (auto-downloads script on first use if missing):

```bash
SCRIPT=~/.claude/scripts/token-stats.py
[ -f "$SCRIPT" ] || (mkdir -p ~/.claude/scripts && curl -fsSL https://raw.githubusercontent.com/clawlabz/claude-token-stats/main/token-stats.py -o "$SCRIPT")
python3 "$SCRIPT" $ARGUMENTS
```

Display the output exactly as returned. Do not summarize or reformat — the script output is already formatted as a table.

If `$ARGUMENTS` is empty, run without arguments (shows 30-day daily summary + model breakdown).

## Usage

```
/token-stats                          # 30-day daily summary + model breakdown (all sources)
/token-stats 2026-03-30               # session breakdown for a specific date
/token-stats --days 7                 # last N days
/token-stats --project claw           # filter by project/cwd keyword
/token-stats 2026-03-30 --project claw
/token-stats --models                 # model breakdown only
/token-stats --source claude          # only Claude Code data
/token-stats --source openclaw        # only OpenClaw data
/token-stats --source codex           # only Codex CLI data
/token-stats --source claude --source openclaw  # multiple sources
```

## Data Sources

| Source | Location | Cost |
|--------|----------|------|
| Claude Code | `~/.claude/projects/` | `~$` estimated |
| OpenClaw | `~/.openclaw/agents/*/sessions/` | `$` stored (Anthropic) |
| QClaw | `~/.qclaw/agents/*/sessions/` | `$` stored (Anthropic) |
| Codex CLI | `~/.codex/sessions/` | `~$` estimated ($0 until pricing published) |
