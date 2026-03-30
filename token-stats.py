#!/usr/bin/env python3
"""
Universal AI Token Usage Statistics
Reads local session logs from Claude Code, OpenClaw, and Codex CLI.

Usage:
  python3 token-stats.py                          # daily summary (last 30 days, all sources)
  python3 token-stats.py 2026-03-30               # session breakdown for a specific date
  python3 token-stats.py --days 7                 # last 7 days
  python3 token-stats.py --project claw           # filter by project/cwd keyword
  python3 token-stats.py --source openclaw        # only OpenClaw data
  python3 token-stats.py --source claude          # only Claude Code data
  python3 token-stats.py --source codex           # only Codex CLI data
  python3 token-stats.py --models                 # model breakdown
"""
import json
import os
import sys
import argparse
from collections import defaultdict
from datetime import datetime, timezone

# ── Pricing (per token, USD) ─────────────────────────────────────────────────

CLAUDE_PRICE = {
    "input":        3.00 / 1_000_000,
    "output":      15.00 / 1_000_000,
    "cache_create": 3.75 / 1_000_000,
    "cache_read":   0.30 / 1_000_000,
}

# Codex CLI — pricing unknown as of 2026-03-30; update when OpenAI publishes
CODEX_PRICE = {
    "input":      0.0 / 1_000_000,
    "output":     0.0 / 1_000_000,
    "cache_read": 0.0 / 1_000_000,
}

PROJECTS_DIR    = os.path.expanduser("~/.claude/projects")
OPENCLAW_DIR    = os.path.expanduser("~/.openclaw")
QCLAW_DIR       = os.path.expanduser("~/.qclaw")
CODEX_SESS_DIR  = os.path.expanduser("~/.codex/sessions")


# ── Cost helpers ──────────────────────────────────────────────────────────────

def _claude_cost(inp, out, cc, cr):
    return (inp * CLAUDE_PRICE["input"]
          + out * CLAUDE_PRICE["output"]
          + cc  * CLAUDE_PRICE["cache_create"]
          + cr  * CLAUDE_PRICE["cache_read"])


def _codex_cost(inp, out, cr):
    return (inp * CODEX_PRICE["input"]
          + out * CODEX_PRICE["output"]
          + cr  * CODEX_PRICE["cache_read"])


def compute_record_cost(r):
    """Return (cost_float, is_estimated) for a record."""
    if not r.get("cost_estimated", True):
        # Stored natively in log — use as-is
        return float(r.get("cost_usd", 0.0)), False
    # Estimate from token counts
    if r.get("source", "") == "codex":
        return _codex_cost(r["inp"], r["out"], r["cr"]), True
    return _claude_cost(r["inp"], r["out"], r["cc"], r["cr"]), True


def hit_ratio(inp, cc, cr):
    denom = inp + cc + cr
    return (cr / denom * 100) if denom > 0 else 0.0


# ── Project label helpers ─────────────────────────────────────────────────────

def short_project(proj_dir_name):
    """Convert ~/.claude/projects dir name to readable label.
    -Users-ludis-Desktop-work-claw -> work/claw
    """
    # Strip leading username prefix
    name = proj_dir_name
    for prefix in ["-Users-ludis-", "-Users-"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    parts = [p for p in name.split("-") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else name


def short_project_from_cwd(cwd):
    """Convert filesystem path to readable label.
    /Users/ludis/Desktop/work/claw -> work/claw
    """
    if not cwd:
        return "(unknown)"
    parts = [p for p in cwd.rstrip("/").split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "(unknown)")


# ── First-message helper ──────────────────────────────────────────────────────

def get_first_user_text(fpath):
    """Return first non-empty, non-command user message text."""
    try:
        with open(fpath, encoding="utf-8") as fp:
            for line in fp:
                try:
                    d = json.loads(line)
                    if d.get("type") not in ("user", "message"):
                        continue
                    msg = d.get("message", d)
                    if isinstance(msg, dict) and msg.get("role") not in (None, "user"):
                        continue
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if isinstance(content, str):
                        text = content.strip()
                    elif isinstance(content, list):
                        text = next(
                            (c.get("text", "") for c in content
                             if isinstance(c, dict) and c.get("type") == "text"),
                            "",
                        ).strip()
                    else:
                        text = ""
                    if text and not text.startswith("<") and not text.startswith("[Image"):
                        return text[:100]
                    if text.startswith("[Image") and "]" in text:
                        tail = text[text.index("]") + 1:].strip()
                        if tail:
                            return tail[:100]
                except Exception:
                    pass
    except Exception:
        pass
    return "(no text)"


# ── Source loaders ────────────────────────────────────────────────────────────

def load_claude_records(project_filter=None):
    """Load records from ~/.claude/projects/"""
    records = []
    if not os.path.isdir(PROJECTS_DIR):
        return records
    for proj_name in os.listdir(PROJECTS_DIR):
        proj_path = os.path.join(PROJECTS_DIR, proj_name)
        if not os.path.isdir(proj_path):
            continue
        if project_filter and project_filter.lower() not in proj_name.lower():
            continue
        label = short_project(proj_name)
        for fname in os.listdir(proj_path):
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(proj_path, fname)
            records.extend(_parse_claude_jsonl(fpath, label))
    return records


def _parse_claude_jsonl(fpath, project_label):
    records = []
    session_id = os.path.splitext(os.path.basename(fpath))[0]
    try:
        with open(fpath, encoding="utf-8") as fp:
            for line in fp:
                try:
                    d = json.loads(line)
                    if d.get("type") != "assistant":
                        continue
                    msg = d.get("message", {})
                    u = msg.get("usage")
                    if not u:
                        continue
                    model = msg.get("model", "unknown")
                    if model in ("<synthetic>", "unknown"):
                        continue
                    ts_str = d.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone()
                    else:
                        ts = datetime.fromtimestamp(os.path.getmtime(fpath)).astimezone()
                    records.append({
                        "date":           ts.strftime("%Y-%m-%d"),
                        "ts":             ts,
                        "model":          model,
                        "inp":            int(u.get("input_tokens", 0) or 0),
                        "out":            int(u.get("output_tokens", 0) or 0),
                        "cc":             int(u.get("cache_creation_input_tokens", 0) or 0),
                        "cr":             int(u.get("cache_read_input_tokens", 0) or 0),
                        "reasoning":      0,
                        "cost_usd":       0.0,
                        "cost_estimated": True,
                        "source":         "claude",
                        "session_id":     session_id,
                        "project":        project_label,
                        "fpath":          fpath,
                    })
                except Exception:
                    pass
    except Exception:
        pass
    return records


def load_openclaw_records(profile_name, base_dir, project_filter=None):
    """Load records from ~/.openclaw/agents/ or ~/.qclaw/agents/"""
    records = []
    agents_dir = os.path.join(base_dir, "agents")
    if not os.path.isdir(agents_dir):
        return records
    for agent_name in sorted(os.listdir(agents_dir)):
        sessions_dir = os.path.join(agents_dir, agent_name, "sessions")
        if not os.path.isdir(sessions_dir):
            continue
        source_label = f"{profile_name}/{agent_name}"
        for fname in sorted(os.listdir(sessions_dir)):
            if not fname.endswith(".jsonl"):
                continue
            if ".jsonl.reset." in fname:
                continue  # archived reset files
            fpath = os.path.join(sessions_dir, fname)
            session_id = fname[:-6]  # strip .jsonl
            records.extend(
                _parse_openclaw_jsonl(fpath, session_id, source_label, project_filter)
            )
    return records


def _parse_openclaw_jsonl(fpath, session_id, source_label, project_filter):
    records = []
    cwd = None
    try:
        with open(fpath, encoding="utf-8") as fp:
            for line in fp:
                try:
                    d = json.loads(line)
                    # grab cwd from session header (first type=session entry)
                    if cwd is None and d.get("type") == "session":
                        cwd = d.get("cwd", "")
                    if d.get("type") != "message":
                        continue
                    msg = d.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    u = msg.get("usage")
                    if not u:
                        continue
                    if project_filter and project_filter.lower() not in (cwd or "").lower():
                        continue
                    ts_str = d.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone()
                    else:
                        ts = datetime.fromtimestamp(os.path.getmtime(fpath)).astimezone()
                    provider = msg.get("provider", "")
                    is_anthropic = (provider == "anthropic")
                    cost_raw = float((u.get("cost") or {}).get("total", 0.0))
                    records.append({
                        "date":           ts.strftime("%Y-%m-%d"),
                        "ts":             ts,
                        "model":          msg.get("model", "unknown"),
                        "inp":            int(u.get("input", 0) or 0),
                        "out":            int(u.get("output", 0) or 0),
                        "cc":             int(u.get("cacheWrite", 0) or 0),
                        "cr":             int(u.get("cacheRead", 0) or 0),
                        "reasoning":      0,
                        "cost_usd":       cost_raw,
                        "cost_estimated": not is_anthropic,
                        "source":         source_label,
                        "session_id":     session_id,
                        "project":        short_project_from_cwd(cwd or ""),
                        "fpath":          fpath,
                    })
                except Exception:
                    pass
    except Exception:
        pass
    return records


def load_codex_records(project_filter=None):
    """Load records from ~/.codex/sessions/YYYY/MM/DD/*.jsonl"""
    records = []
    if not os.path.isdir(CODEX_SESS_DIR):
        return records
    for year in sorted(os.listdir(CODEX_SESS_DIR)):
        ypath = os.path.join(CODEX_SESS_DIR, year)
        if not os.path.isdir(ypath) or not year.isdigit():
            continue
        for month in sorted(os.listdir(ypath)):
            mpath = os.path.join(ypath, month)
            if not os.path.isdir(mpath):
                continue
            for day in sorted(os.listdir(mpath)):
                dpath = os.path.join(mpath, day)
                if not os.path.isdir(dpath):
                    continue
                for fname in sorted(os.listdir(dpath)):
                    if not fname.endswith(".jsonl"):
                        continue
                    fpath = os.path.join(dpath, fname)
                    session_id = fname[:-6]
                    records.extend(_parse_codex_jsonl(fpath, session_id, project_filter))
    return records


def _parse_codex_jsonl(fpath, session_id, project_filter):
    records = []
    last_model = "codex/unknown"
    last_cwd = ""
    try:
        with open(fpath, encoding="utf-8") as fp:
            for line in fp:
                try:
                    d = json.loads(line)
                    if d.get("type") == "turn_context":
                        p = d.get("payload", {})
                        last_model = p.get("model", last_model)
                        last_cwd   = p.get("cwd", last_cwd)
                    if d.get("type") != "event_msg":
                        continue
                    p = d.get("payload", {})
                    if p.get("type") != "token_count":
                        continue
                    info = p.get("info")
                    if not info:
                        continue
                    lu = info.get("last_token_usage") or {}
                    inp = int(lu.get("input_tokens", 0) or 0)
                    out = int(lu.get("output_tokens", 0) or 0)
                    cr  = int(lu.get("cached_input_tokens", 0) or 0)
                    rsn = int(lu.get("reasoning_output_tokens", 0) or 0)
                    if inp == 0 and out == 0:
                        continue
                    if project_filter and project_filter.lower() not in last_cwd.lower():
                        continue
                    ts_str = d.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone()
                    else:
                        ts = datetime.fromtimestamp(os.path.getmtime(fpath)).astimezone()
                    records.append({
                        "date":           ts.strftime("%Y-%m-%d"),
                        "ts":             ts,
                        "model":          last_model,
                        "inp":            inp,
                        "out":            out,
                        "cc":             0,
                        "cr":             cr,
                        "reasoning":      rsn,
                        "cost_usd":       0.0,
                        "cost_estimated": True,
                        "source":         "codex",
                        "session_id":     session_id,
                        "project":        short_project_from_cwd(last_cwd),
                        "fpath":          fpath,
                    })
                except Exception:
                    pass
    except Exception:
        pass
    return records


def load_all_records(sources=None, project_filter=None):
    """Load and merge records from all enabled sources."""
    active = set(sources) if sources else {"claude", "openclaw", "qclaw", "codex"}
    records = []
    if "claude" in active:
        records.extend(load_claude_records(project_filter))
    if "openclaw" in active:
        records.extend(load_openclaw_records("openclaw", OPENCLAW_DIR, project_filter))
    if "qclaw" in active:
        records.extend(load_openclaw_records("qclaw", QCLAW_DIR, project_filter))
    if "codex" in active:
        records.extend(load_codex_records(project_filter))
    return records


# ── Aggregation ───────────────────────────────────────────────────────────────

def agg_records(records, key_fn):
    """Aggregate records by key_fn. Returns dict of key -> agg_dict."""
    agg = defaultdict(lambda: {
        "inp": 0, "out": 0, "cc": 0, "cr": 0, "reasoning": 0,
        "cost": 0.0, "any_estimated": False,
        "model_tokens": defaultdict(int),
        "sessions": set(),
        "sources": set(),
    })
    for r in records:
        k = key_fn(r)
        a = agg[k]
        a["inp"]       += r["inp"]
        a["out"]       += r["out"]
        a["cc"]        += r["cc"]
        a["cr"]        += r["cr"]
        a["reasoning"] += r.get("reasoning", 0)
        c, est = compute_record_cost(r)
        a["cost"]          += c
        a["any_estimated"]  = a["any_estimated"] or est
        total = r["inp"] + r["cc"] + r["cr"] + r["out"]
        a["model_tokens"][r["model"]] += total
        a["sessions"].add(r["session_id"])
        a["sources"].add(r.get("source", "?"))
    return agg


# ── Display helpers ───────────────────────────────────────────────────────────

def fmt_tok(n):
    """Format token count as human-readable (84.3M, 423.9K, 512)."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def fmt_cost(cost_val, estimated):
    """Format cost with ~$ or $ prefix."""
    prefix = "~$" if estimated else " $"
    return f"{prefix}{cost_val:>9.4f}"


def parse_model_name(m):
    """claude-opus-4-6-thinking -> Opus4.6✦  |  gpt-5.3-codex -> GPT5.3"""
    if not m or m in ("<synthetic>", "unknown", "codex/unknown", "delivery-mirror"):
        return None
    thinking = m.endswith("-thinking")
    base = m.replace("-thinking", "")
    # Claude models: claude-{family}-{major}-{minor}[-{date}]
    if base.startswith("claude-"):
        parts = base.split("-")  # ['claude','sonnet','4','6'] or ['claude','sonnet','4','5','20251001']
        if len(parts) >= 4:
            family  = parts[1].capitalize()
            version = f"{parts[2]}.{parts[3]}"
            label   = f"{family}{version}"
            return label + ("✦" if thinking else "")
    # GPT models: gpt-5.3-codex, gpt-4o, etc.
    if base.startswith("gpt-"):
        parts = base.split("-")  # ['gpt','5.3','codex'] or ['gpt','4o']
        version = parts[1] if len(parts) > 1 else base
        return f"GPT{version}"
    # Gemini models
    if "gemini" in base.lower():
        return base.replace("gemini-", "Gemini").replace("-", "")
    # Other: return as-is (truncated)
    return base[:12]


def model_short(model_tokens):
    """model_tokens: {model_name: total_tokens} -> 'Opus4.6+Sonnet4.6'"""
    seen = []
    for m in sorted(model_tokens.keys(), key=lambda x: -model_tokens[x]):
        label = parse_model_name(m)
        if label and label not in seen:
            seen.append(label)
    return "+".join(seen) or "?"


# ── Views ─────────────────────────────────────────────────────────────────────

def view_daily(records, days=30):
    from datetime import date, timedelta
    today    = date.today()
    cutoff   = (today - timedelta(days=days - 1)).isoformat()
    records  = [r for r in records if r["date"] >= cutoff]

    # Detect active sources for footer
    active_sources = {r.get("source", "claude") for r in records}
    has_openclaw   = any(s.startswith(("openclaw/", "qclaw/")) for s in active_sources)
    has_codex      = "codex" in active_sources
    has_gpt_zero   = any(
        r.get("source", "").startswith(("openclaw/", "qclaw/"))
        and not r["model"].startswith("claude")
        and not r.get("cost_estimated", True)
        for r in records
    )

    # Group by (date, source)
    by_date_source = agg_records(records, lambda r: (r["date"], r.get("source", "claude")))

    # Collect all dates
    all_dates = sorted({k[0] for k in by_date_source.keys()}, reverse=True)

    W_SRC  = 22
    W_DATE = 12
    LINE_W = W_DATE + W_SRC + 68
    sep    = "─" * LINE_W

    print(f"\n{'Date':<{W_DATE}} {'Source':<{W_SRC}} {'Sess':>5} {'TotalInput':>11} {'Output':>9} {'CacheHit%':>10} {'Total':>9}  {'Cost':>12}  Models")
    print(sep)

    grand = {"inp":0,"out":0,"cc":0,"cr":0,"cost":0.0,"any_estimated":False,"sessions":set(),"model_tokens":defaultdict(int)}

    for d in all_dates:
        # Collect sources for this date, sorted
        date_sources = sorted(k[1] for k in by_date_source if k[0] == d)
        date_totals  = {"inp":0,"out":0,"cc":0,"cr":0,"cost":0.0,"any_est":False,"sessions":set(),"model_tokens":defaultdict(int)}

        for src in date_sources:
            a       = by_date_source[(d, src)]
            t_inp   = a["inp"] + a["cc"] + a["cr"]
            t_all   = t_inp + a["out"]
            hr      = hit_ratio(a["inp"], a["cc"], a["cr"])
            models  = model_short(a["model_tokens"])
            nsess   = len(a["sessions"])
            cost_s  = fmt_cost(a["cost"], a["any_estimated"])
            print(f"{d:<{W_DATE}} {src:<{W_SRC}} {nsess:>5} {fmt_tok(t_inp):>11} {fmt_tok(a['out']):>9} {hr:>9.1f}% {fmt_tok(t_all):>9}  {cost_s}  {models}")
            # accumulate date totals
            date_totals["inp"]  += a["inp"]; date_totals["out"] += a["out"]
            date_totals["cc"]   += a["cc"];  date_totals["cr"]  += a["cr"]
            date_totals["cost"] += a["cost"]
            date_totals["any_est"] = date_totals["any_est"] or a["any_estimated"]
            date_totals["sessions"].update(a["sessions"])
            for m, t in a["model_tokens"].items():
                date_totals["model_tokens"][m] += t

        # If multiple sources on this date, print a day total row
        if len(date_sources) > 1:
            t_inp  = date_totals["inp"] + date_totals["cc"] + date_totals["cr"]
            t_all  = t_inp + date_totals["out"]
            hr     = hit_ratio(date_totals["inp"], date_totals["cc"], date_totals["cr"])
            models = model_short(date_totals["model_tokens"])
            nsess  = len(date_totals["sessions"])
            cost_s = fmt_cost(date_totals["cost"], date_totals["any_est"])
            print(f"{d:<{W_DATE}} {'  ALL':<{W_SRC}} {nsess:>5} {fmt_tok(t_inp):>11} {fmt_tok(date_totals['out']):>9} {hr:>9.1f}% {fmt_tok(t_all):>9}  {cost_s}  {models}")

        # Accumulate grand totals
        grand["inp"]  += date_totals["inp"]; grand["out"] += date_totals["out"]
        grand["cc"]   += date_totals["cc"];  grand["cr"]  += date_totals["cr"]
        grand["cost"] += date_totals["cost"]
        grand["any_estimated"] = grand["any_estimated"] or date_totals["any_est"]
        grand["sessions"].update(date_totals["sessions"])
        for m, t in date_totals["model_tokens"].items():
            grand["model_tokens"][m] += t

    print(sep)
    g_inp  = grand["inp"] + grand["cc"] + grand["cr"]
    g_all  = g_inp + grand["out"]
    g_hr   = hit_ratio(grand["inp"], grand["cc"], grand["cr"])
    g_sess = len(grand["sessions"])
    g_cost = fmt_cost(grand["cost"], grand["any_estimated"])
    g_mod  = model_short(grand["model_tokens"])
    print(f"{'TOTAL':<{W_DATE}} {'':<{W_SRC}} {g_sess:>5} {fmt_tok(g_inp):>11} {fmt_tok(grand['out']):>9} {g_hr:>9.1f}% {fmt_tok(g_all):>9}  {g_cost}  {g_mod}")

    # Footer
    print(f"\n  TotalInput = fresh({fmt_tok(grand['inp'])}) + cache_write({fmt_tok(grand['cc'])}) + cache_read({fmt_tok(grand['cr'])})")
    print(f"  Cost legend:  $ = stored in log   ~$ = estimated from pricing table")
    if has_gpt_zero:
        print(f"  OpenClaw non-Anthropic models: tokens counted, cost = $0.0000 (no local pricing)")
    if has_codex:
        print(f"  Codex CLI: cost shown as ~$0 (pricing not yet published by OpenAI)")


def view_sessions(records, target_date):
    day_records = [r for r in records if r["date"] == target_date]
    if not day_records:
        print(f"No records found for {target_date}")
        return

    # Group by (source, session_id)
    agg = agg_records(day_records, lambda r: (r.get("source","claude"), r["session_id"]))

    # First message and time range per session
    first_msgs = {}
    times      = defaultdict(lambda: {"start": None, "end": None})
    projects   = {}
    for r in day_records:
        k = (r.get("source","claude"), r["session_id"])
        if k not in first_msgs:
            first_msgs[k] = get_first_user_text(r["fpath"])
            projects[k]   = r["project"]
        ts = r["ts"]
        if times[k]["start"] is None or ts < times[k]["start"]:
            times[k]["start"] = ts
        if times[k]["end"] is None or ts > times[k]["end"]:
            times[k]["end"] = ts

    W_SRC  = 22
    W_PROJ = 16
    LINE_W = 7 + W_SRC + W_PROJ + 70
    sep    = "─" * LINE_W

    print(f"\nSessions on {target_date}")
    print(sep)
    print(f"{'Time':<7} {'Source':<{W_SRC}} {'Project':<{W_PROJ}} {'Msgs':>5} {'TotalInput':>11} {'Output':>9} {'CacheHit%':>10} {'Cost':>12}  Topic")
    print(sep)

    keys_sorted = sorted(agg.keys(), key=lambda k: times[k]["start"] or datetime.min)

    total_cost = 0.0
    any_est    = False
    for key in keys_sorted:
        src, sid = key
        a        = agg[key]
        t_inp    = a["inp"] + a["cc"] + a["cr"]
        hr       = hit_ratio(a["inp"], a["cc"], a["cr"])
        nsess_msgs = sum(1 for r in day_records if (r.get("source","claude"), r["session_id"]) == key)
        start    = times[key]["start"]
        time_str = start.strftime("%H:%M") if start else "?"
        proj     = projects.get(key, "")[:W_PROJ]
        topic    = first_msgs.get(key, "")[:40]
        cost_s   = fmt_cost(a["cost"], a["any_estimated"])
        total_cost += a["cost"]
        any_est     = any_est or a["any_estimated"]
        print(f"{time_str:<7} {src:<{W_SRC}} {proj:<{W_PROJ}} {nsess_msgs:>5} {fmt_tok(t_inp):>11} {fmt_tok(a['out']):>9} {hr:>9.1f}%  {cost_s}  {topic}")

    print(sep)
    all_inp = sum(a["inp"] for a in agg.values())
    all_out = sum(a["out"] for a in agg.values())
    all_cc  = sum(a["cc"]  for a in agg.values())
    all_cr  = sum(a["cr"]  for a in agg.values())
    t_inp   = all_inp + all_cc + all_cr
    hr      = hit_ratio(all_inp, all_cc, all_cr)
    cost_s  = fmt_cost(total_cost, any_est)
    print(f"{'TOTAL':<{7+W_SRC+W_PROJ}} {fmt_tok(t_inp):>11} {fmt_tok(all_out):>9} {hr:>9.1f}%  {cost_s}")
    print(f"\n  TotalInput = fresh({fmt_tok(all_inp)}) + cache_write({fmt_tok(all_cc)}) + cache_read({fmt_tok(all_cr)})")
    print(f"  Cost legend:  $ = stored in log   ~$ = estimated from pricing table")


def view_model_breakdown(records, days=30):
    from datetime import date, timedelta
    today   = date.today()
    cutoff  = (today - timedelta(days=days - 1)).isoformat()
    records = [r for r in records if r["date"] >= cutoff]

    agg = agg_records(records, lambda r: r["model"])

    label = f"last {days} days" if days > 1 else records[0]["date"] if records else "?"
    print(f"\nModel breakdown ({label})")
    print("─" * 110)
    print(f"{'Short':<15} {'Model ID':<40} {'TotalInput':>11} {'Output':>9} {'Total':>9}  {'Cost':>12}")
    print("─" * 110)
    for m in sorted(agg.keys(), key=lambda x: -agg[x]["cost"]):
        if m in ("<synthetic>", "unknown", "codex/unknown", "delivery-mirror"):
            continue
        a      = agg[m]
        t_inp  = a["inp"] + a["cc"] + a["cr"]
        t_all  = t_inp + a["out"]
        lbl    = parse_model_name(m) or m
        cost_s = fmt_cost(a["cost"], a["any_estimated"])
        print(f"{lbl:<15} {m:<40} {fmt_tok(t_inp):>11} {fmt_tok(a['out']):>9} {fmt_tok(t_all):>9}  {cost_s}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Universal AI token usage statistics")
    parser.add_argument("date",     nargs="?", help="Date (YYYY-MM-DD) for session breakdown")
    parser.add_argument("--days",   type=int, default=30, help="Days for daily summary (default: 30)")
    parser.add_argument("--project","-p", help="Filter by project/cwd keyword")
    parser.add_argument("--models", action="store_true", help="Show model breakdown")
    parser.add_argument("--source", "-s", action="append", dest="sources",
                        choices=["claude", "openclaw", "qclaw", "codex"],
                        help="Filter to source(s). Repeatable. Default: all.")
    args = parser.parse_args()

    sources      = args.sources  # None = all
    source_label = ", ".join(sorted(set(sources))) if sources else "all sources"
    print(f"Loading records ({source_label}) ...")

    records = load_all_records(sources=sources, project_filter=args.project)

    n_sess = len({r["session_id"] for r in records})
    src_counts = defaultdict(int)
    for r in records:
        src_counts[r.get("source","?").split("/")[0]] += 1
    src_summary = "  ".join(f"{s}={c:,}" for s, c in sorted(src_counts.items()))
    print(f"Loaded {len(records):,} records from {n_sess:,} sessions  [{src_summary}]\n")

    if args.date:
        view_sessions(records, args.date)
        print()
        view_model_breakdown([r for r in records if r["date"] == args.date], days=1)
    elif args.models:
        view_model_breakdown(records, days=args.days)
    else:
        view_daily(records, days=args.days)
        print()
        view_model_breakdown(records, days=args.days)


if __name__ == "__main__":
    main()
