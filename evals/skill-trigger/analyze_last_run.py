#!/usr/bin/env python3
"""Cost / latency / vote-agreement analysis over a saved trigger-eval run.

Reads `last_run.json` (or any saved run) and emits a markdown report covering:

  - Per-skill TPR/FPR (sanity recap)
  - Vote-agreement breakdown (how often did K voters agree unanimously)
  - Per-skill / overall latency stats (mean, p50, p95) IF per-query
    duration_s was captured by the runner. Older runs without this field
    fall back to total elapsed_s only.
  - Estimated NIM token usage. Token counts are NOT in the saved run, so we
    compute a *char-based estimate* (chars/4 ≈ tokens). This is a floor
    estimate intended for "is this expensive?" answers, not billing.
  - Ambiguity case results (if present in the run).

The script is deliberately read-only and post-hoc: no LLM calls, no network.
This means a human can re-generate the report any time without burning tokens.

Usage:
    python evals/skill-trigger/analyze_last_run.py
    python evals/skill-trigger/analyze_last_run.py --run last_ambiguity_run.json
    python evals/skill-trigger/analyze_last_run.py --markdown report.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

# Rough token/char ratio for English-ish prompts. NIM tokenizers vary; this
# is the OpenAI-style 4-chars-per-token rule of thumb.
CHARS_PER_TOKEN = 4

# Approximate USD per 1M output tokens for the NIM models we use. Used only
# for an order-of-magnitude cost estimate. Real billing depends on contract.
NIM_PRICE_PER_M_TOKENS_USD = {
    "nemotron": 0.50,
    "mistral":  0.40,
    "qwen":     0.40,
    "deepseek": 0.30,
    "gemma":    0.30,
}


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    if p <= 0:
        return xs[0]
    if p >= 100:
        return xs[-1]
    k = (len(xs) - 1) * (p / 100)
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _latency_stats(durations_s: list[float]) -> dict:
    if not durations_s:
        return {}
    return {
        "n": len(durations_s),
        "mean_s": round(statistics.mean(durations_s), 2),
        "p50_s":  round(_percentile(durations_s, 50), 2),
        "p95_s":  round(_percentile(durations_s, 95), 2),
        "max_s":  round(max(durations_s), 2),
        "total_s": round(sum(durations_s), 1),
    }


def _estimate_token_cost(report: dict) -> dict:
    """Char-based token estimate. Each per_query has the system+user prompt;
    we approximate prompt size from the skill_descriptions block + the query
    text. Output tokens ≈ 30 (a small JSON pick); we use that fixed estimate.
    """
    descs = report.get("skill_descriptions_evaluated", {})
    # System prompt = sum of all skill descriptions + boilerplate.
    sys_chars = sum(len(d) for d in descs.values()) + 400  # +boilerplate
    n_queries = len(report.get("per_query", [])) + len(report.get("ambiguity_results", []))
    if not n_queries:
        return {}

    # Per query, count user prompt = the query string.
    queries: list[str] = [q["query"] for q in report.get("per_query", [])]
    queries += [a["query"] for a in report.get("ambiguity_results", [])]
    user_chars_total = sum(len(q) for q in queries)

    # Each query is sent to ALL voters (K voters per query), so multiply.
    # Voter count = max votes seen on any successful query.
    voter_count = 0
    for q in (report.get("per_query") or []) + (report.get("ambiguity_results") or []):
        voter_count = max(voter_count, len(q.get("votes", [])))
    voter_count = max(voter_count, 1)

    prompt_tokens = (sys_chars * n_queries + user_chars_total) * voter_count // CHARS_PER_TOKEN
    output_tokens = 30 * n_queries * voter_count

    # Average price across configured voters as a single number.
    voter_names = set()
    for q in (report.get("per_query") or []) + (report.get("ambiguity_results") or []):
        for v in q.get("votes", []):
            voter_names.add(v.get("voter", ""))
    prices = [NIM_PRICE_PER_M_TOKENS_USD.get(v, 0.40) for v in voter_names]
    avg_price = sum(prices) / max(len(prices), 1) if prices else 0.40

    cost_usd = (prompt_tokens + output_tokens) / 1_000_000 * avg_price
    return {
        "voter_count": voter_count,
        "prompt_tokens_estimate": prompt_tokens,
        "output_tokens_estimate": output_tokens,
        "total_tokens_estimate": prompt_tokens + output_tokens,
        "estimated_cost_usd": round(cost_usd, 4),
        "method": f"char-based estimate (~{CHARS_PER_TOKEN} chars/token), "
                  f"output capped at 30 tok/query — order-of-magnitude only",
    }


def _vote_agreement(per_query: list[dict]) -> dict:
    """How often did all K voters agree?

    confidence == 1.0 means all voters agreed on the picked answer.
    < 1.0 means at least one disagreed.
    """
    if not per_query:
        return {}
    unanimous = sum(1 for q in per_query if q.get("confidence", 0) >= 0.99)
    split = len(per_query) - unanimous
    return {
        "queries": len(per_query),
        "unanimous": unanimous,
        "unanimous_pct": round(100 * unanimous / len(per_query), 1),
        "split_decision": split,
    }


def build_report(run: dict) -> str:
    lines: list[str] = []
    lines.append("# Trigger Eval — Cost & Latency Analysis")
    lines.append("")

    summary = run.get("per_skill_summary", {})
    if summary:
        lines.append("## Per-skill TPR / FPR (recap)")
        lines.append("")
        lines.append("| Skill | TPR | FPR |")
        lines.append("|---|---|---|")
        for name, s in sorted(summary.items()):
            lines.append(f"| {name} | {s['true_positive_rate']:.2f} | "
                         f"{s['false_positive_rate']:.2f} |")
        lines.append("")

    pq = run.get("per_query", [])
    durations = [q["duration_s"] for q in pq if q.get("duration_s")]
    if durations:
        lines.append("## Latency (per-query, K-voter parallel call)")
        lines.append("")
        overall = _latency_stats(durations)
        lines.append(f"- N: {overall['n']}, total wall-clock: {overall['total_s']}s")
        lines.append(f"- mean: {overall['mean_s']}s, p50: {overall['p50_s']}s, "
                     f"p95: {overall['p95_s']}s, max: {overall['max_s']}s")
        lines.append("")
        # Per-skill latency breakdown
        per_skill_dur: dict[str, list[float]] = {}
        for q in pq:
            if q.get("duration_s"):
                per_skill_dur.setdefault(q["target_skill"], []).append(q["duration_s"])
        if per_skill_dur:
            lines.append("| Skill | n | mean | p50 | p95 | max |")
            lines.append("|---|---|---|---|---|---|")
            for skill in sorted(per_skill_dur):
                s = _latency_stats(per_skill_dur[skill])
                lines.append(f"| {skill} | {s['n']} | {s['mean_s']}s | "
                             f"{s['p50_s']}s | {s['p95_s']}s | {s['max_s']}s |")
            lines.append("")
    else:
        lines.append("## Latency")
        lines.append("")
        lines.append(f"- per-query duration not captured in this run; "
                     f"total elapsed: {run.get('elapsed_s', '?')}s")
        lines.append("- Re-run with the instrumented runner to populate per-query "
                     "timing (`evals/skill-trigger/runner.py` records `duration_s` "
                     "on each query as of 2026-05-03).")
        lines.append("")

    cost = _estimate_token_cost(run)
    if cost:
        lines.append("## Token / cost estimate (char-based)")
        lines.append("")
        lines.append(f"- Voter count per query: {cost['voter_count']} (K-vote)")
        lines.append(f"- Prompt tokens (estimate): {cost['prompt_tokens_estimate']:,}")
        lines.append(f"- Output tokens (estimate): {cost['output_tokens_estimate']:,}")
        lines.append(f"- Total tokens (estimate): {cost['total_tokens_estimate']:,}")
        lines.append(f"- Estimated cost: ~${cost['estimated_cost_usd']:.4f} USD")
        lines.append(f"- Method: {cost['method']}")
        lines.append("")

    vote = _vote_agreement(pq)
    if vote:
        lines.append("## K-voter agreement")
        lines.append("")
        lines.append(f"- Queries: {vote['queries']}")
        lines.append(f"- Unanimous (all voters agreed): {vote['unanimous']} "
                     f"({vote['unanimous_pct']}%)")
        lines.append(f"- Split decisions: {vote['split_decision']}")
        lines.append("")

    amb = run.get("ambiguity_results", [])
    if amb:
        strict = sum(1 for a in amb if a.get("is_pass"))
        lenient = sum(1 for a in amb if a.get("voters_in_allowed_count", 0) > 0)
        lines.append("## Cross-domain ambiguity cases")
        lines.append("")
        lines.append(f"- Strict (majority in allowed set): **{strict}/{len(amb)}**")
        lines.append(f"- Lenient (any voter in allowed set): **{lenient}/{len(amb)}**")
        lines.append("")
        lines.append("| # | Query | Picked | Allowed | Strict | Lenient |")
        lines.append("|---|---|---|---|---|---|")
        for i, a in enumerate(amb, 1):
            allowed = [a["primary"]] + list(a.get("also_acceptable", []))
            short_q = a["query"] if len(a["query"]) <= 50 else a["query"][:47] + "..."
            strict_mark = "PASS" if a["is_pass"] else "FAIL"
            voters_ok = a.get("voters_in_allowed_count", 0)
            voters_n = a.get("voters_total", len(a.get("votes", [])))
            lenient_mark = f"{voters_ok}/{voters_n}"
            lines.append(f"| {i} | `{short_q}` | `{a['picked']}` | "
                         f"`{','.join(allowed)}` | {strict_mark} | {lenient_mark} |")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path,
                   default=Path(__file__).resolve().parent / "last_run.json",
                   help="Saved run JSON to analyze")
    p.add_argument("--markdown", type=Path, default=None,
                   help="Optional: write report to this path instead of stdout")
    args = p.parse_args()

    if not args.run.exists():
        print(f"run file not found: {args.run}")
        return 2
    run = json.loads(args.run.read_text())
    md = build_report(run)
    if args.markdown:
        args.markdown.write_text(md)
        print(f"wrote: {args.markdown}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
