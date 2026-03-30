#!/usr/bin/env python3
"""
Claude Code Token Usage Statistics
Usage:
  python3 token-stats.py                     # daily summary (last 30 days, all projects)
  python3 token-stats.py 2026-03-30          # session breakdown for a specific date
  python3 token-stats.py --days 7            # last 7 days
  python3 token-stats.py --project claw      # filter by project name keyword
  python3 token-stats.py 2026-03-30 --project claw
"""
import json
import os
import sys
import argparse
from collections import defaultdict
from datetime import datetime, timezone

# ── Pricing (per token, USD) ─────────────────────────────────────────────────
PRICE = {
    "input":        3.00 / 1_000_000,
    "output":      15.00 / 1_000_000,
    "cache_create": 3.75 / 1_000_000,
    "cache_read":   0.30 / 1_000_000,
}

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")


def cost(inp, out, cc, cr):
    return inp * PRICE["input"] + out * PRICE["output"] + cc * PRICE["cache_create"] + cr * PRICE["cache_read"]


def hit_ratio(inp, cc, cr):
    denom = inp + cc + cr
    return (cr / denom * 100) if denom > 0 else 0.0


def short_project(proj_dir_name):
    """Convert -Users-ludis-Desktop-work-claw -> claw"""
    parts = proj_dir_name.replace("-Users-ludis-", "").split("-")
    # take last meaningful segment(s)
    result = "/".join(parts[-2:]) if len(parts) >= 2 else proj_dir_name
    return result.lstrip("-")


def get_first_user_text(fpath):
    """Return first non-empty, non-command user message text."""
    try:
        with open(fpath, encoding="utf-8") as fp:
            for line in fp:
                try:
                    d = json.loads(line)
                    if d.get("type") != "user":
                        continue
                    msg = d.get("message", d)
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        text = content.strip()
                    elif isinstance(content, list):
                        text = next(
                            (c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"),
                            "",
                        ).strip()
                    else:
                        text = ""
                    # skip system/command wrappers
                    if text and not text.startswith("<") and not text.startswith("[Image"):
                        return text[:100]
                    # try text that has image prefix but also real text
                    if text.startswith("[Image") and "]" in text:
                        tail = text[text.index("]") + 1:].strip()
                        if tail:
                            return tail[:100]
                except Exception:
                    pass
    except Exception:
        pass
    return "(no text)"


def parse_jsonl(fpath, project_label):
    """
    Returns list of dicts:
      {date, ts, model, inp, out, cc, cr, session_id, project}
    One entry per assistant message with usage data.
    """
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
                    ts_str = d.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        # convert to local time for date display
                        local_ts = ts.astimezone()
                        date = local_ts.strftime("%Y-%m-%d")
                    else:
                        # fallback: file mtime
                        mtime = os.path.getmtime(fpath)
                        local_ts = datetime.fromtimestamp(mtime)
                        date = local_ts.strftime("%Y-%m-%d")

                    records.append({
                        "date": date,
                        "ts": local_ts,
                        "model": msg.get("model", "unknown"),
                        "inp": u.get("input_tokens", 0),
                        "out": u.get("output_tokens", 0),
                        "cc": u.get("cache_creation_input_tokens", 0),
                        "cr": u.get("cache_read_input_tokens", 0),
                        "session_id": session_id,
                        "project": project_label,
                        "fpath": fpath,
                    })
                except Exception:
                    pass
    except Exception:
        pass
    return records


def load_all_records(project_filter=None):
    """Load all records from all project directories, optionally filtered."""
    records = []
    if not os.path.isdir(PROJECTS_DIR):
        return records
    for proj_name in os.listdir(PROJECTS_DIR):
        proj_path = os.path.join(PROJECTS_DIR, proj_name)
        if not os.path.isdir(proj_path):
            continue
        label = short_project(proj_name)
        if project_filter and project_filter.lower() not in proj_name.lower():
            continue
        for fname in os.listdir(proj_path):
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(proj_path, fname)
            records.extend(parse_jsonl(fpath, label))
    return records


# ── Aggregation helpers ───────────────────────────────────────────────────────

def agg_key(records, key_fn):
    agg = defaultdict(lambda: {"inp": 0, "out": 0, "cc": 0, "cr": 0, "models": set(), "sessions": set()})
    for r in records:
        k = key_fn(r)
        a = agg[k]
        a["inp"] += r["inp"]
        a["out"] += r["out"]
        a["cc"] += r["cc"]
        a["cr"] += r["cr"]
        a["models"].add(r["model"])
        a["sessions"].add(r["session_id"])
    return agg


# ── Display helpers ───────────────────────────────────────────────────────────

def fmt_num(n):
    return f"{n:>13,}"


def model_short(models):
    names = []
    for m in sorted(models):
        if "opus" in m:
            names.append("Opus")
        elif "sonnet" in m:
            names.append("Sonnet")
        elif "haiku" in m:
            names.append("Haiku")
        else:
            names.append(m.split("-")[1] if "-" in m else m)
    return "+".join(sorted(set(names))) or "?"


# ── Views ─────────────────────────────────────────────────────────────────────

def fmt_tok(n):
    """Format token count as human-readable (e.g. 84.3M, 423.9K)."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def view_daily(records, days=30):
    from datetime import date, timedelta
    today = date.today()
    cutoff = (today - timedelta(days=days - 1)).isoformat()
    records = [r for r in records if r["date"] >= cutoff]

    agg = agg_key(records, lambda r: r["date"])

    # total_input = inp (fresh) + cc (cache write) + cr (cache read)
    # This is what the model actually processed on input side
    print(f"\n{'Date':<12} {'Sess':>5} {'TotalInput':>11} {'Output':>9} {'(CacheHit%)':>12} {'Total':>10} {'Cost(USD)':>11}  Models")
    print(f"{'':12} {'':5} {'=inp+cc+cr':>11} {'':9} {'cr/(inp+cc+cr)':>12} {'':10}")
    print("─" * 95)

    total_cost = 0.0
    for d in sorted(agg.keys(), reverse=True):
        a = agg[d]
        c = cost(a["inp"], a["out"], a["cc"], a["cr"])
        total_cost += c
        total_inp = a["inp"] + a["cc"] + a["cr"]
        total_all = total_inp + a["out"]
        hr = hit_ratio(a["inp"], a["cc"], a["cr"])
        models = model_short(a["models"])
        nsess = len(a["sessions"])
        print(f"{d:<12} {nsess:>5} {fmt_tok(total_inp):>11} {fmt_tok(a['out']):>9} {hr:>11.1f}% {fmt_tok(total_all):>10} ${c:>10.4f}  {models}")

    print("─" * 95)
    all_inp = sum(a["inp"] for a in agg.values())
    all_out = sum(a["out"] for a in agg.values())
    all_cc  = sum(a["cc"]  for a in agg.values())
    all_cr  = sum(a["cr"]  for a in agg.values())
    all_total_inp = all_inp + all_cc + all_cr
    all_total = all_total_inp + all_out
    all_hr  = hit_ratio(all_inp, all_cc, all_cr)
    all_sess = len({r["session_id"] for r in records})
    print(f"{'TOTAL':<12} {all_sess:>5} {fmt_tok(all_total_inp):>11} {fmt_tok(all_out):>9} {all_hr:>11.1f}% {fmt_tok(all_total):>10} ${total_cost:>10.4f}")
    print(f"\n  TotalInput breakdown: fresh={fmt_tok(all_inp)}  cache_write={fmt_tok(all_cc)}  cache_read={fmt_tok(all_cr)}")
    print(f"  Note: OpenClaw gateway calls NOT included (direct Anthropic API, not logged locally)")


def view_sessions(records, target_date):
    day_records = [r for r in records if r["date"] == target_date]
    if not day_records:
        print(f"No records found for {target_date}")
        return

    # group by (project, session_id)
    agg = agg_key(day_records, lambda r: (r["project"], r["session_id"]))

    # get first message per session
    first_msgs = {}
    for r in day_records:
        k = (r["project"], r["session_id"])
        if k not in first_msgs:
            first_msgs[k] = get_first_user_text(r["fpath"])

    # get time range per session
    times = defaultdict(lambda: {"start": None, "end": None})
    for r in day_records:
        k = (r["project"], r["session_id"])
        ts = r["ts"]
        if times[k]["start"] is None or ts < times[k]["start"]:
            times[k]["start"] = ts
        if times[k]["end"] is None or ts > times[k]["end"]:
            times[k]["end"] = ts

    print(f"\nSessions on {target_date}")
    print("─" * 110)
    header = f"{'Time':<7} {'Project':<18} {'Msgs':>5} {'TotalInput':>11} {'Output':>9} {'CacheHit%':>10} {'Total':>9} {'Cost':>9}  {'Models':<10}  Topic"
    print(header)
    print("─" * 110)

    # sort by start time
    keys_sorted = sorted(agg.keys(), key=lambda k: times[k]["start"] or datetime.min)

    total_cost = 0.0
    for key in keys_sorted:
        proj, sid = key
        a = agg[key]
        c = cost(a["inp"], a["out"], a["cc"], a["cr"])
        total_cost += c
        total_inp = a["inp"] + a["cc"] + a["cr"]
        total_all = total_inp + a["out"]
        hr = hit_ratio(a["inp"], a["cc"], a["cr"])
        models = model_short(a["models"])
        start = times[key]["start"]
        time_str = start.strftime("%H:%M") if start else "?"
        msg_count = sum(1 for r in day_records if (r["project"], r["session_id"]) == key)
        topic = first_msgs.get(key, "")[:45]
        print(f"{time_str:<7} {proj:<18} {msg_count:>5} {fmt_tok(total_inp):>11} {fmt_tok(a['out']):>9} {hr:>9.1f}% {fmt_tok(total_all):>9} ${c:>8.4f}  {models:<10}  {topic}")

    print("─" * 110)
    all_inp = sum(a["inp"] for a in agg.values())
    all_out = sum(a["out"] for a in agg.values())
    all_cc  = sum(a["cc"]  for a in agg.values())
    all_cr  = sum(a["cr"]  for a in agg.values())
    all_total_inp = all_inp + all_cc + all_cr
    all_total = all_total_inp + all_out
    all_hr  = hit_ratio(all_inp, all_cc, all_cr)
    print(f"{'TOTAL':<31} {fmt_tok(all_total_inp):>11} {fmt_tok(all_out):>9} {all_hr:>9.1f}% {fmt_tok(all_total):>9} ${total_cost:>8.4f}")
    print(f"\n  TotalInput = fresh({fmt_tok(all_inp)}) + cache_write({fmt_tok(all_cc)}) + cache_read({fmt_tok(all_cr)})")


def view_model_breakdown(records, days=30):
    from datetime import date, timedelta
    today = date.today()
    cutoff = (today - timedelta(days=days - 1)).isoformat()
    records = [r for r in records if r["date"] >= cutoff]

    agg = agg_key(records, lambda r: r["model"])

    print(f"\nModel breakdown (last {days} days)")
    print("─" * 85)
    print(f"{'Model':<35} {'TotalInput':>11} {'Output':>9} {'Total':>9} {'Cost(USD)':>11}")
    print("─" * 85)
    for m in sorted(agg.keys()):
        a = agg[m]
        c = cost(a["inp"], a["out"], a["cc"], a["cr"])
        total_inp = a["inp"] + a["cc"] + a["cr"]
        total_all = total_inp + a["out"]
        print(f"{m:<35} {fmt_tok(total_inp):>11} {fmt_tok(a['out']):>9} {fmt_tok(total_all):>9} ${c:>10.4f}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Claude Code token usage stats")
    parser.add_argument("date", nargs="?", help="Date (YYYY-MM-DD) for session breakdown")
    parser.add_argument("--days", type=int, default=30, help="Number of days for daily summary (default: 30)")
    parser.add_argument("--project", "-p", help="Filter by project name keyword")
    parser.add_argument("--models", action="store_true", help="Show model breakdown")
    args = parser.parse_args()

    print(f"Loading records from {PROJECTS_DIR} ...")
    records = load_all_records(project_filter=args.project)
    print(f"Loaded {len(records):,} API call records from {len(set(r['session_id'] for r in records))} sessions\n")

    if args.date:
        view_sessions(records, args.date)
        print()
        view_model_breakdown(
            [r for r in records if r["date"] == args.date], days=1
        )
    elif args.models:
        view_model_breakdown(records, days=args.days)
    else:
        view_daily(records, days=args.days)
        print()
        view_model_breakdown(records, days=args.days)


if __name__ == "__main__":
    main()
