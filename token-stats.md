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
/token-stats                          # 30-day daily summary + model breakdown
/token-stats 2026-03-30               # session breakdown for a specific date
/token-stats --days 7                 # last N days
/token-stats --project claw           # filter by project name keyword
/token-stats 2026-03-30 --project claw
/token-stats --models                 # model breakdown only
```
