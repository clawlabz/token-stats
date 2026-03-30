# claude-token-stats

A Claude Code slash command (`/token-stats`) that gives you a detailed breakdown of your token usage, cache hit rates, and estimated costs — directly from local session files.

No API calls required. Reads from `~/.claude/projects/` on your machine.

## What it shows

**Daily summary** (default):

```
Date         Sessions      Input    Output  CacheCreate     CacheRead  HitRatio   Cost(USD)  Models
────────────────────────────────────────────────────────────────────────────────────────────────────
2026-03-30          7      1,246   202,232    1,752,681    81,541,542     97.9% $   34.07  Sonnet
2026-03-29          7      3,902   360,066    3,524,440   280,678,766     98.8% $  102.83  Opus+Sonnet
...
TOTAL             158 44,044,560 9,508,643  175,982,936 6,672,339,059     96.8% $ 2936.40
```

**Session breakdown** (per day):

```
Time          Project              Messages     Input   Output  CacheCreate     CacheRead   HR%      Cost  Models        Topic
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
00:21         work/claw                 112       134   25,362      245,686    15,041,752   98% $  5.81  Sonnet  litebase迁移完毕了吗？
02:17         work/claw                 441       626   99,167      873,874    43,963,929   98% $ 17.96  Sonnet  整体迁移完毕了吗？还有遗留事项吗
```

**Model breakdown**:

```
Model                                    Input    Output     CacheRead   Cost(USD)
────────────────────────────────────────────────────────────────────────────────
claude-opus-4-6                      7,451,990 8,064,789 6,510,381,462 $ 2732.54
claude-opus-4-6-thinking            34,311,728 1,032,081    21,607,016 $  124.90
claude-sonnet-4-6                    2,280,842   411,773   140,350,581 $   78.96
```

Column reference:
- **HitRatio** = `CacheRead / (Input + CacheCreate + CacheRead)` — higher is better (saves cost)
- **CacheCreate** — tokens written to cache (costs 1.25x input price, paid once)
- **CacheRead** — tokens read from cache (costs 0.10x input price, very cheap)
- **Cost** — estimated cost at API list prices (not actual Max subscription billing)

## Installation

1. **Clone or download** this repo
2. **Copy the script** to `~/.claude/scripts/`:
   ```bash
   mkdir -p ~/.claude/scripts
   cp token-stats.py ~/.claude/scripts/
   ```
3. **Copy the command** to `~/.claude/commands/`:
   ```bash
   mkdir -p ~/.claude/commands
   cp token-stats.md ~/.claude/commands/
   ```

That's it. The `/token-stats` command is now available in any Claude Code session.

## Usage

Inside Claude Code, type:

```
/token-stats                          # 30-day daily summary + model breakdown
/token-stats 2026-03-30               # session breakdown for a specific date
/token-stats --days 7                 # last 7 days
/token-stats --project claw           # filter by project name keyword
/token-stats 2026-03-30 --project claw
/token-stats --models                 # model breakdown only
```

You can also run the script directly from your terminal:

```bash
python3 ~/.claude/scripts/token-stats.py
python3 ~/.claude/scripts/token-stats.py 2026-03-30
python3 ~/.claude/scripts/token-stats.py --days 7 --project claw
```

## Requirements

- Python 3.8+
- Claude Code (the session JSONL files it writes to `~/.claude/projects/`)

## Pricing used for cost estimates

The script uses Anthropic API list prices:

| Token type    | Price per million |
|---------------|-------------------|
| Input         | $3.00             |
| Output        | $15.00            |
| Cache create  | $3.75             |
| Cache read    | $0.30             |

> **Note**: If you use Claude Max (subscription), actual billing differs. These estimates reflect what the equivalent API usage would cost.

## What's NOT included

- **OpenClaw / third-party gateway calls**: API calls made by external processes (e.g. OpenClaw gateway) go directly to the Anthropic API and are not logged by Claude Code. Those only appear in the Anthropic billing dashboard or tools like [sub2usage](https://github.com/ferrucc-io/sub2usage).
- **Other Claude clients**: Claude.ai web, mobile app, etc. are not captured here.

## How it works

Claude Code saves every conversation turn to JSONL files under `~/.claude/projects/<project-path>/`. Each assistant message includes a `usage` field with exact token counts broken down by type (input, output, cache_creation, cache_read) plus the model name and a timestamp. This script parses all those files across all your projects.

## License

MIT
