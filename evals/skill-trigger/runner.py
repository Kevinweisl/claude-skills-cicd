"""Trigger-eval runner — quantifies whether each skill's SKILL.md description
triggers Claude precisely.

Methodology adapted from Anthropic's skill-creator (`run_loop.py`):
  - For each query, present the LLM with the full list of skill descriptions
    and ask which skill (or NONE) it would invoke.
  - Use a K=3 ensemble vote across DeepSeek + Nemotron + Mistral so per-call
    noise doesn't dominate.
  - Score per skill: TPR (should_trigger correctly picked the skill) and
    FPR (should_not_trigger queries incorrectly picked the skill).
  - Confusion matrix shows which skill pairs get conflated.

Reproducing this run:
  Requires NVIDIA NIM API access (set NIM_API_KEY env var) plus the
  `shared.llm_client.vote_role` helper that this repo's split-off doesn't
  ship — it lives in the original mono-repo because three repos share it.
  The runner therefore lazy-imports it inside main(); the file can be read
  / inspected / linted without the dep, but a real run will fail with a
  clear ImportError if you try to execute it standalone.

  For evaluator review, the saved artefacts are the authoritative output:
    - last_run.json / last_ambiguity_run.json : full per-query vote records
    - cost_report_140q.md / cost_report_ambiguity.md : aggregated reports
    - analyze_last_run.py : regenerates reports from saved JSON without
                            calling any LLM (offline, free, deterministic).

Usage (only works in the mono-repo with shared/ available):
    python evals/skill-trigger/runner.py
    python evals/skill-trigger/runner.py --skill lint-and-test  # only one
    python evals/skill-trigger/runner.py --queries-file path/to/custom.json

Output:
  - stdout markdown report
  - evals/skill-trigger/last_run.json with raw votes for trend tracking
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# The actual LLM voter is lazy-imported inside main() so the rest of this
# file (parsing, scoring, report formatting) can be inspected / linted /
# unit-tested even when shared/ isn't available in this repo split.
import yaml  # noqa: E402

NONE_LABEL = "NONE"


def _parse_skill_frontmatter(md_path: Path) -> dict:
    """Read YAML frontmatter from a SKILL.md. Returns {name, description, ...}."""
    text = md_path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    return yaml.safe_load(text[4:end]) or {}


def _load_skill_descriptions(skills_dir: Path) -> dict[str, str]:
    """Read every skills/*/SKILL.md and return {name: description}.

    Skips underscore-prefixed dirs (e.g. _shared).
    """
    out: dict[str, str] = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        md = skill_dir / "SKILL.md"
        if not md.exists():
            continue
        fm = _parse_skill_frontmatter(md)
        name = fm.get("name", skill_dir.name)
        desc = fm.get("description", "")
        if desc:
            out[name] = desc
    return out


def _build_messages(skill_descs: dict[str, str], query: str) -> list[dict]:
    skills_block = "\n".join(
        f"### {name}\n{desc.strip()}\n" for name, desc in skill_descs.items()
    )
    system = f"""\
You are Claude with these skills available. For each user query, decide which ONE skill best matches, or reply NONE if no skill applies.

AVAILABLE SKILLS:

{skills_block}

Reply with ONLY the JSON object below — no prose, no markdown:
{{"skill": "<one of: {', '.join(skill_descs)}, NONE>"}}
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]


def _parse_skill_pick(raw: str, valid_skills: set[str]) -> str:
    """Extract skill name from LLM response. Raises on malformed/unknown."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not m:
            raise ValueError(f"no JSON in response: {raw[:200]!r}") from None
        parsed = json.loads(m.group(0))
    pick = parsed.get("skill", "")
    if not isinstance(pick, str):
        raise ValueError(f"missing skill string: {parsed!r}")
    pick = pick.strip()
    if pick.upper() == NONE_LABEL:
        return NONE_LABEL
    if pick not in valid_skills:
        raise ValueError(f"unknown skill {pick!r}; valid: {valid_skills}")
    return pick


async def evaluate_query(
    skill_descs: dict[str, str], query: str,
) -> tuple[str, float, list, float]:
    """Returns (picked_skill, confidence, raw_votes_list, duration_s).

    duration_s is wall-clock for the K=N parallel vote (the slowest voter
    dominates), so per-query latency tracking is meaningful for cost reports.
    """
    # Lazy import: shared.llm_client lives in the original mono-repo, not
    # in this split. Importing only on actual run lets file-level inspection
    # (linting / reading / unit-testing the parsing helpers above) work.
    try:
        from shared.llm_client import vote_role
    except ImportError as exc:
        raise ImportError(
            "shared.llm_client is not available in this repo split. "
            "To re-run the eval, use the original mono-repo or replicate "
            "the NIM K=3 vote helper locally. The saved last_run.json and "
            "cost_report_*.md files are the authoritative artefacts; use "
            "analyze_last_run.py to regenerate reports without calling LLMs."
        ) from exc

    valid = set(skill_descs)
    messages = _build_messages(skill_descs, query)
    parser = lambda raw: _parse_skill_pick(raw, valid)
    t0 = time.perf_counter()
    vote = await vote_role(
        "trigger_eval",
        messages=messages,
        parser=parser,
        fallback=NONE_LABEL,
        max_tokens=128,
        temperature=0.0,
        timeout=60.0,
    )
    duration_s = time.perf_counter() - t0
    return vote.pick, vote.confidence, vote.votes, duration_s


def _build_skill_summary(per_query, target_skill):
    """For target_skill: count TP/FN on should_trigger, FP/TN on should_not_trigger."""
    tp = fn = fp = tn = 0
    for q in per_query:
        picked = q["picked"]
        is_should_trigger = q["expected_label"] == "should_trigger"
        if is_should_trigger:
            if picked == target_skill:
                tp += 1
            else:
                fn += 1
        else:
            if picked == target_skill:
                fp += 1
            else:
                tn += 1
    n_should = tp + fn
    n_should_not = fp + tn
    tpr = tp / n_should if n_should else 0.0
    fpr = fp / n_should_not if n_should_not else 0.0
    return {
        "true_positive": tp, "false_negative": fn,
        "false_positive": fp, "true_negative": tn,
        "true_positive_rate": round(tpr, 3),
        "false_positive_rate": round(fpr, 3),
        "n_should_trigger": n_should,
        "n_should_not_trigger": n_should_not,
    }


def _build_confusion_matrix(per_query) -> dict:
    """{ground_truth_skill_or_NONE: {picked_skill: count}}."""
    matrix: dict = defaultdict(lambda: defaultdict(int))
    for q in per_query:
        gt = q["target_skill"] if q["expected_label"] == "should_trigger" else NONE_LABEL
        matrix[gt][q["picked"]] += 1
    return {k: dict(v) for k, v in matrix.items()}


async def run_eval(queries_file: Path, skills_dir: Path,
                   *, only_skill: str | None = None,
                   only_ambiguity: bool = False) -> dict:
    spec = json.loads(queries_file.read_text())
    skill_descs = _load_skill_descriptions(skills_dir)
    skills_in_corpus = list(spec["skills"])
    if only_ambiguity:
        eval_skills: list[str] = []
    elif only_skill:
        eval_skills = [only_skill]
    else:
        eval_skills = skills_in_corpus

    per_query: list[dict] = []
    t0 = time.perf_counter()

    # Run queries in parallel batches per-skill so the user sees progress
    for target_skill in eval_skills:
        if target_skill not in spec["skills"]:
            print(f"[skip] skill {target_skill!r} not in corpus", file=sys.stderr)
            continue
        skill_block = spec["skills"][target_skill]
        q_blocks = []
        for label in ("should_trigger", "should_not_trigger"):
            for query in skill_block.get(label, []):
                q_blocks.append((label, query))
        print(f"\n[{target_skill}] running {len(q_blocks)} queries...", flush=True)
        results = await asyncio.gather(*(
            evaluate_query(skill_descs, query) for _, query in q_blocks
        ), return_exceptions=True)
        for (label, query), res in zip(q_blocks, results, strict=True):
            if isinstance(res, BaseException):
                per_query.append({
                    "target_skill": target_skill,
                    "expected_label": label,
                    "query": query,
                    "picked": "ERROR",
                    "confidence": 0.0,
                    "votes": [],
                    "duration_s": 0.0,
                    "error": f"{type(res).__name__}: {res}",
                })
                continue
            picked, confidence, votes, duration_s = res
            per_query.append({
                "target_skill": target_skill,
                "expected_label": label,
                "query": query,
                "picked": picked,
                "confidence": round(confidence, 2),
                "votes": [{"voter": v[0], "pick": v[1]} for v in votes],
                "duration_s": round(duration_s, 3),
            })

    # Cross-domain ambiguity cases — pass = picked in {primary} ∪ also_acceptable
    ambiguity_results: list[dict] = []
    cases = spec.get("ambiguity_cases", [])
    if cases and (only_ambiguity or not only_skill):
        print(f"\n[ambiguity] running {len(cases)} cross-domain cases...", flush=True)
        amb_results = await asyncio.gather(*(
            evaluate_query(skill_descs, c["query"]) for c in cases
        ), return_exceptions=True)
        for case, res in zip(cases, amb_results, strict=True):
            allowed = {case["primary_skill"]} | set(case.get("also_acceptable", []))
            if isinstance(res, BaseException):
                ambiguity_results.append({
                    "query": case["query"],
                    "primary": case["primary_skill"],
                    "also_acceptable": case.get("also_acceptable", []),
                    "picked": "ERROR",
                    "is_pass": False,
                    "confidence": 0.0,
                    "votes": [],
                    "duration_s": 0.0,
                    "note": case.get("note", ""),
                    "error": f"{type(res).__name__}: {res}",
                })
                continue
            picked, conf, votes, duration_s = res
            voters_in_allowed = sum(1 for v in votes if v[1] in allowed)
            ambiguity_results.append({
                "query": case["query"],
                "primary": case["primary_skill"],
                "also_acceptable": case.get("also_acceptable", []),
                "picked": picked,
                "is_pass": picked in allowed,
                # Lenient signal: did ANY individual voter land in the allowed
                # set? Useful for diagnosing K=N tie-break NONE-fallbacks where
                # the majority rule masks per-voter agreement.
                "voters_in_allowed_count": voters_in_allowed,
                "voters_total": len(votes),
                "confidence": round(conf, 2),
                "votes": [{"voter": v[0], "pick": v[1]} for v in votes],
                "duration_s": round(duration_s, 3),
                "note": case.get("note", ""),
            })

    elapsed = time.perf_counter() - t0

    # Per-skill summary and confusion matrix
    per_skill_summary = {}
    for skill in eval_skills:
        skill_queries = [q for q in per_query if q["target_skill"] == skill]
        per_skill_summary[skill] = _build_skill_summary(skill_queries, skill)
    confusion = _build_confusion_matrix(per_query)

    return {
        "per_query": per_query,
        "per_skill_summary": per_skill_summary,
        "confusion_matrix": confusion,
        "ambiguity_results": ambiguity_results,
        "elapsed_s": round(elapsed, 1),
        "skill_descriptions_evaluated": skill_descs,
    }


def print_markdown_report(report: dict) -> None:
    print()
    print("# Skill Trigger Eval Report")
    print()
    print(f"**Elapsed:** {report['elapsed_s']}s, "
          f"**Queries:** {len(report['per_query'])}")
    print()
    print("## Per-skill TPR / FPR")
    print()
    print("| Skill | TPR | FPR | TP | FN | FP | TN |")
    print("|---|---|---|---|---|---|---|")
    for skill, s in sorted(report["per_skill_summary"].items()):
        print(f"| {skill} | {s['true_positive_rate']:.2f} | {s['false_positive_rate']:.2f} "
              f"| {s['true_positive']} | {s['false_negative']} "
              f"| {s['false_positive']} | {s['true_negative']} |")
    print()
    print("## Confusion matrix (rows = ground truth, cols = picked)")
    print()
    skills = sorted({q["target_skill"] for q in report["per_query"]} | {NONE_LABEL})
    header = ["**↓gt / picked→**"] + skills + ["ERROR"]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for gt in sorted(report["confusion_matrix"]):
        row = [f"**{gt}**"]
        for col in skills + ["ERROR"]:
            count = report["confusion_matrix"][gt].get(col, 0)
            row.append(str(count) if count else "—")
        print("| " + " | ".join(row) + " |")

    # Notable misses
    misses = []
    for q in report["per_query"]:
        is_should = q["expected_label"] == "should_trigger"
        if is_should and q["picked"] != q["target_skill"]:
            misses.append(("FN", q))
        if (not is_should) and q["picked"] == q["target_skill"]:
            misses.append(("FP", q))
    if misses:
        print()
        print(f"## Misses ({len(misses)})")
        print()
        for kind, q in misses:
            print(f"- **{kind}** {q['target_skill']}: query={q['query']!r}, "
                  f"picked={q['picked']!r}, conf={q['confidence']}")

    amb = report.get("ambiguity_results", [])
    if amb:
        passed = sum(1 for a in amb if a.get("is_pass"))
        any_voter_passed = sum(
            1 for a in amb if a.get("voters_in_allowed_count", 0) > 0
        )
        print()
        print(f"## Ambiguity cases — {passed}/{len(amb)} pass (strict majority); "
              f"{any_voter_passed}/{len(amb)} pass (lenient: any voter in allowed)")
        print()
        print("| # | Query | Picked | Allowed | Pass? |")
        print("|---|---|---|---|---|")
        for i, a in enumerate(amb, 1):
            allowed_set = [a["primary"]] + list(a.get("also_acceptable", []))
            mark = "✅" if a["is_pass"] else "❌"
            short_q = a["query"] if len(a["query"]) <= 60 else a["query"][:57] + "..."
            print(f"| {i} | `{short_q}` | `{a['picked']}` | "
                  f"`{','.join(allowed_set)}` | {mark} |")
        fails = [a for a in amb if not a["is_pass"]]
        if fails:
            print()
            print("### Ambiguity failures")
            print()
            for a in fails:
                print(f"- query: `{a['query']}`")
                print(f"  - picked: `{a['picked']}` (conf={a['confidence']})")
                print(f"  - allowed: `{[a['primary'], *a.get('also_acceptable', [])]}`")
                print(f"  - note: {a.get('note', '')}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--queries-file", type=Path,
                   default=Path(__file__).resolve().parent / "queries.json")
    p.add_argument("--skills-dir", type=Path, default=ROOT / "skills")
    p.add_argument("--skill", type=str, default=None,
                   help="Run only this skill's queries (for iterative tuning)")
    p.add_argument("--only-ambiguity", action="store_true",
                   help="Skip per-skill batches; run only the cross-domain cases")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "last_run.json")
    args = p.parse_args()

    if not args.queries_file.exists():
        print(f"queries file not found: {args.queries_file}", file=sys.stderr)
        return 2

    report = asyncio.run(run_eval(args.queries_file, args.skills_dir,
                                  only_skill=args.skill,
                                  only_ambiguity=args.only_ambiguity))
    args.out.write_text(json.dumps(report, indent=2, default=str))
    print_markdown_report(report)
    print(f"\n(Raw votes saved to {args.out})")

    # Exit code reflects: any skill TPR < 0.8 OR FPR > 0.2 → non-zero
    # Ambiguity-only runs gate on >=70% pass rate instead.
    if args.only_ambiguity:
        amb = report.get("ambiguity_results", [])
        if not amb:
            return 0
        passed = sum(1 for a in amb if a.get("is_pass"))
        return 0 if passed / len(amb) >= 0.7 else 1
    bad = any(
        s["true_positive_rate"] < 0.8 or s["false_positive_rate"] > 0.2
        for s in report["per_skill_summary"].values()
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
