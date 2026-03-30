# Token Usage Statistics

Run the token usage stats script with the provided arguments.

## Usage

```
/token-stats                          # daily summary, last 30 days
/token-stats 2026-03-30               # session breakdown for that date
/token-stats --days 7                 # last 7 days
/token-stats --project claw           # filter by project
/token-stats 2026-03-30 --project claw
/token-stats --models                 # model breakdown only
```

## Instructions

Run the following bash command using the arguments provided in `$ARGUMENTS`:

```bash
python3 ~/.claude/scripts/token-stats.py $ARGUMENTS
```

Display the output exactly as returned. Do not summarize or reformat — the script output is already formatted as a table.

If `$ARGUMENTS` is empty, run without arguments (shows 30-day daily summary + model breakdown).

After displaying the output, add a brief one-line note explaining what each column means if the user seems unfamiliar with the output.
