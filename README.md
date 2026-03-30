# claude-token-stats

A Claude Code slash command (`/token-stats`) that gives you a detailed breakdown of your token usage, cache hit rates, and estimated costs — directly from local session files.

No API calls required. Reads from `~/.claude/projects/` on your machine.

## What it shows

**Daily summary** (default):

```
Date          Sess  TotalInput    Output  (CacheHit%)      Total   Cost(USD)  Models
                    =inp+cc+cr           cr/(inp+cc+cr)
───────────────────────────────────────────────────────────────────────────────────────────────
2026-03-30       8       86.3M    215.5K        97.8%      86.5M $   35.52  Sonnet
2026-03-29       7      284.2M    360.1K        98.8%     284.6M $  102.83  Opus+Sonnet
───────────────────────────────────────────────────────────────────────────────────────────────
TOTAL           14      370.5M    575.5K        98.5%     371.1M $  138.36

  TotalInput breakdown: fresh=5.2K  cache_write=5.4M  cache_read=365.1M
```

**Session breakdown** (per day):

```
Time    Project             Msgs  TotalInput    Output  CacheHit%     Total      Cost  Models      Topic
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
00:21   work/claw            112       15.3M     25.4K      98.4%     15.3M $  5.81  Sonnet  litebase迁移完毕了吗？
02:17   work/claw            441       44.8M     99.2K      98.0%     44.9M $ 17.96  Sonnet  整体迁移完毕了吗？还有遗留事项吗

  TotalInput = fresh(1.3K) + cache_write(1.9M) + cache_read(84.1M)
```

**Model breakdown**:

```
Model                                TotalInput    Output     Total   Cost(USD)
─────────────────────────────────────────────────────────────────────────────────────
claude-opus-4-6                          252.1M    265.5K    252.4M $   89.83
claude-sonnet-4-6                        118.4M    310.0K    118.7M $   48.53
```

Column reference:
- **TotalInput** = `input_tokens + cache_creation_tokens + cache_read_tokens` — all tokens the model actually processed on the input side
- **CacheHit%** = `cache_read / TotalInput` — higher means more cache reuse (much cheaper per token)
- **Total** = TotalInput + Output — grand total tokens processed
- **Cost** — estimated cost at API list prices (not actual Max subscription billing)

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/clawlabz/claude-token-stats/main/install.sh | bash
```

Restart Claude Code — `/token-stats` is ready.

> The command also **self-heals**: if the script is ever missing, it re-downloads automatically on the next `/token-stats` run.

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
