"""Score a RAG run-*.json against a Wiki run-*.json with an LLM judge.

For each question, blinds the two answers as System A and System B (the
mapping is recorded so results can be un-blinded), feeds them to a Judge
LLM along with the rubric, parses the structured score response, and
writes a `judged-<timestamp>.json` artifact with per-question scores
plus aggregated means by system, criterion, and tier.

Cross-family judging is the default (`gpt-5.4`) to avoid same-family
self-preference bias when scoring Claude outputs. An optional
`--secondary-judge` runs a second model on a subset for inter-rater
reliability.

Usage:
    python -m scripts.judge_runs \\
        --rag-run experiments/results/run-20260504T210000Z.json \\
        --wiki-run path/to/wiki-run.json \\
        --rubric experiments/rubric.yaml \\
        [--judge-model gpt-5.4] [--reasoning-effort medium] \\
        [--secondary-judge gemini-2.5-pro --secondary-judge-questions Q1,Q2,Q3] \\
        [--seed 42] [--dry-run] [--max-questions N] [--resume PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts._common import err, info, utc_timestamp, write_json

DEFAULT_JUDGE_MODEL = "gpt-5.4"
DEFAULT_REASONING_EFFORT = "medium"  # Judging is less reasoning-heavy than synthesis.
DEFAULT_RESULTS_DIR = "experiments/results"

# Maps each system label internally; A/B in the prompt is randomized per question.
SYSTEM_RAG = "rag"
SYSTEM_WIKI = "wiki"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Criterion:
    id: str
    label: str
    description: str
    anchors: dict[str, str]


@dataclass
class Rubric:
    criteria: list[Criterion]
    path: Path

    @property
    def ids(self) -> list[str]:
        return [c.id for c in self.criteria]


@dataclass
class QuestionRecord:
    """One question's answers from both systems, ready to judge."""

    id: str
    tier: str
    bias: str
    text: str
    rag_answer: str
    rag_sources: list[dict]
    rag_metadata: dict
    wiki_answer: str
    wiki_sources: list[dict]
    wiki_metadata: dict


@dataclass
class JudgmentResult:
    question_id: str
    tier: str
    bias: str
    judge_model: str
    blinding: dict[str, str]  # {"A": "rag" | "wiki", "B": "rag" | "wiki"}
    rag_scores: dict[str, int | None]
    wiki_scores: dict[str, int | None]
    notes: str
    raw_response: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_rubric(path: Path) -> Rubric:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "criteria" not in raw:
        raise ValueError(f"rubric file missing 'criteria:' key: {path}")
    criteria = [
        Criterion(
            id=c["id"],
            label=c.get("label", c["id"]),
            description=str(c.get("description", "")).strip(),
            anchors={k: str(v).strip() for k, v in (c.get("anchors") or {}).items()},
        )
        for c in raw["criteria"]
    ]
    if not criteria:
        raise ValueError(f"rubric has no criteria: {path}")
    return Rubric(criteria=criteria, path=path)


def load_run(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or "results" not in raw:
        raise ValueError(f"run file missing 'results:' key: {path}")
    return raw


def pair_runs(rag_run: dict, wiki_run: dict) -> list[QuestionRecord]:
    """Match results by question id. Skips any unmatched ids with a warning."""
    rag_by_id = {r["id"]: r for r in rag_run["results"]}
    wiki_by_id = {r["id"]: r for r in wiki_run["results"]}

    common = sorted(set(rag_by_id) & set(wiki_by_id))
    only_rag = sorted(set(rag_by_id) - set(wiki_by_id))
    only_wiki = sorted(set(wiki_by_id) - set(rag_by_id))
    if only_rag:
        info(f"warning: {len(only_rag)} question(s) only in RAG run: {only_rag}")
    if only_wiki:
        info(f"warning: {len(only_wiki)} question(s) only in Wiki run: {only_wiki}")

    out: list[QuestionRecord] = []
    for qid in common:
        rag = rag_by_id[qid]
        wiki = wiki_by_id[qid]
        out.append(
            QuestionRecord(
                id=qid,
                tier=str(rag.get("tier", wiki.get("tier", ""))),
                bias=str(rag.get("bias", wiki.get("bias", ""))),
                text=str(rag.get("text") or wiki.get("text") or ""),
                rag_answer=str(rag.get("answer", "")),
                rag_sources=list(rag.get("sources") or []),
                rag_metadata=dict(rag.get("metadata") or {}),
                wiki_answer=str(wiki.get("answer", "")),
                wiki_sources=list(wiki.get("sources") or []),
                wiki_metadata=dict(wiki.get("metadata") or {}),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Blinding
# ---------------------------------------------------------------------------


def blind(rng: random.Random, qid: str) -> dict[str, str]:
    """Deterministically assign rag/wiki to A/B per question.

    Using a single rng across questions in iteration order makes the entire
    run reproducible from --seed alone. The qid argument is unused but kept
    for symmetry/extension (e.g. per-question deterministic salts later).
    """
    del qid  # reserved for future per-question salting
    if rng.random() < 0.5:
        return {"A": SYSTEM_RAG, "B": SYSTEM_WIKI}
    return {"A": SYSTEM_WIKI, "B": SYSTEM_RAG}


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


JUDGE_SYSTEM_PROMPT = """\
You are an evaluator scoring two answers (System A and System B) to the \
same research-corpus question. Score each system independently on each \
criterion. Use the anchors to calibrate; a 5 is genuinely middling, not a \
default. Do NOT compare the two systems against each other in your scores \
— score each one against the rubric on its own merits.

Return your answer as a single JSON object with exactly this shape:
{
  "system_a": {<criterion_id>: <int 1-10>, ...},
  "system_b": {<criterion_id>: <int 1-10>, ...},
  "notes": "<2-3 sentence explanation of any score that's especially high or low>"
}

Do not include any text outside the JSON object.\
"""


def format_sources(sources: list[dict]) -> str:
    if not sources:
        return "(no sources retrieved)"
    parts = []
    for i, s in enumerate(sources, 1):
        filename = s.get("filename", "unknown")
        pages = s.get("page_numbers") or []
        score = s.get("relevance_score")
        text = s.get("chunk_text", "").strip()
        header = f"[Source {i}] {filename}"
        if pages:
            header += f" (p. {', '.join(str(p) for p in pages)})"
        if score is not None:
            header += f" — score {score:.3f}"
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


def format_rubric(rubric: Rubric) -> str:
    parts = []
    for c in rubric.criteria:
        parts.append(f"### {c.label} (id: `{c.id}`)\n{c.description}")
        for level, anchor in c.anchors.items():
            parts.append(f"- **{level}**: {anchor}")
        parts.append("")
    return "\n".join(parts)


def build_user_prompt(
    record: QuestionRecord,
    blinding: dict[str, str],
    rubric: Rubric,
) -> str:
    a_system = blinding["A"]
    b_system = blinding["B"]
    a_answer = record.rag_answer if a_system == SYSTEM_RAG else record.wiki_answer
    a_sources = record.rag_sources if a_system == SYSTEM_RAG else record.wiki_sources
    b_answer = record.rag_answer if b_system == SYSTEM_RAG else record.wiki_answer
    b_sources = record.rag_sources if b_system == SYSTEM_RAG else record.wiki_sources

    return f"""\
## Question

Tier: {record.tier} | Expected bias: {record.bias}

{record.text}

## Rubric

Score each system 1–10 on each criterion below.

{format_rubric(rubric)}

## System A — answer

{a_answer or "(empty)"}

### System A — retrieved sources

{format_sources(a_sources)}

## System B — answer

{b_answer or "(empty)"}

### System B — retrieved sources

{format_sources(b_sources)}

Return your scores now as the JSON object specified in the system prompt."""


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------


def parse_judge_response(
    raw: str, criterion_ids: list[str]
) -> tuple[dict[str, int | None], dict[str, int | None], str, str | None]:
    """Extract per-system per-criterion scores from a Judge response.

    Returns (system_a_scores, system_b_scores, notes, error).
    Permissive about JSON-with-prose-around-it but strict about score type.
    """
    payload = _extract_json_object(raw)
    if payload is None:
        empty = {cid: None for cid in criterion_ids}
        return empty, empty, "", f"could not parse JSON from judge response"

    a_scores = _coerce_scores(payload.get("system_a") or {}, criterion_ids)
    b_scores = _coerce_scores(payload.get("system_b") or {}, criterion_ids)
    notes = str(payload.get("notes") or "").strip()
    error: str | None = None
    missing_a = [k for k, v in a_scores.items() if v is None]
    missing_b = [k for k, v in b_scores.items() if v is None]
    if missing_a or missing_b:
        error = (
            f"missing or invalid scores — system_a: {missing_a}, system_b: {missing_b}"
        )
    return a_scores, b_scores, notes, error


def _extract_json_object(text: str) -> dict | None:
    """Find the first balanced { … } region in `text` and json-load it."""
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def _coerce_scores(
    raw: dict, criterion_ids: list[str]
) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for cid in criterion_ids:
        val = raw.get(cid)
        if isinstance(val, bool):  # bool is subtype of int in Python — exclude
            out[cid] = None
            continue
        if isinstance(val, int):
            out[cid] = val if 1 <= val <= 10 else None
        elif isinstance(val, float) and val.is_integer():
            ival = int(val)
            out[cid] = ival if 1 <= ival <= 10 else None
        else:
            out[cid] = None
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate(
    judgments: list[JudgmentResult], criterion_ids: list[str]
) -> dict:
    """Compute per-system per-criterion means + per-tier breakdowns.

    Skips judgments that errored out (rag_scores will be all None) so a
    single bad judgment doesn't poison the means.
    """
    by_tier: dict[str, list[JudgmentResult]] = {}
    for j in judgments:
        by_tier.setdefault(j.tier or "untiered", []).append(j)

    def _mean(values: list[int]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 3)

    def _aggregate_group(group: list[JudgmentResult]) -> dict:
        out: dict = {"n": len(group), "rag": {}, "wiki": {}}
        for cid in criterion_ids:
            rag_vals = [j.rag_scores[cid] for j in group if j.rag_scores.get(cid) is not None]
            wiki_vals = [j.wiki_scores[cid] for j in group if j.wiki_scores.get(cid) is not None]
            out["rag"][cid] = _mean([int(v) for v in rag_vals if v is not None])
            out["wiki"][cid] = _mean([int(v) for v in wiki_vals if v is not None])
        return out

    return {
        "overall": _aggregate_group(judgments),
        "by_tier": {tier: _aggregate_group(g) for tier, g in by_tier.items()},
    }


# ---------------------------------------------------------------------------
# Judge invocation
# ---------------------------------------------------------------------------


def make_litellm_kwargs(reasoning_effort: str) -> dict:
    """Build the kwargs dict passed to litellm.acompletion.

    OpenAI o1/gpt-5 reasoning models accept a `reasoning_effort` parameter
    (low/medium/high). LiteLLM passes it through. We always set
    response_format=json_object so the parser doesn't have to fish JSON out
    of prose, but we also extract defensively just in case.
    """
    kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}}
    if reasoning_effort and reasoning_effort != "off":
        kwargs["reasoning_effort"] = reasoning_effort
    return kwargs


async def judge_one(
    record: QuestionRecord,
    rubric: Rubric,
    blinding: dict[str, str],
    judge_model: str,
    reasoning_effort: str,
) -> JudgmentResult:
    """Send one question's blinded answers to the Judge and parse the result."""
    import litellm

    user_prompt = build_user_prompt(record, blinding, rubric)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = await litellm.acompletion(
            model=judge_model,
            messages=messages,
            **make_litellm_kwargs(reasoning_effort),
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        return JudgmentResult(
            question_id=record.id,
            tier=record.tier,
            bias=record.bias,
            judge_model=judge_model,
            blinding=blinding,
            rag_scores={cid: None for cid in rubric.ids},
            wiki_scores={cid: None for cid in rubric.ids},
            notes="",
            raw_response="",
            error=f"{type(e).__name__}: {e}",
        )

    a_scores, b_scores, notes, parse_error = parse_judge_response(raw, rubric.ids)
    rag_scores = a_scores if blinding["A"] == SYSTEM_RAG else b_scores
    wiki_scores = a_scores if blinding["A"] == SYSTEM_WIKI else b_scores

    return JudgmentResult(
        question_id=record.id,
        tier=record.tier,
        bias=record.bias,
        judge_model=judge_model,
        blinding=blinding,
        rag_scores=rag_scores,
        wiki_scores=wiki_scores,
        notes=notes,
        raw_response=raw,
        error=parse_error,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class RunSpec:
    rag_run: Path
    wiki_run: Path
    rubric_path: Path
    judge_model: str
    reasoning_effort: str
    secondary_judge: str | None
    secondary_judge_questions: set[str]
    seed: int
    max_questions: int | None
    resume_path: Path | None
    dry_run: bool
    results_dir: Path


def existing_judgments(path: Path | None) -> dict[tuple[str, str], JudgmentResult]:
    """Load prior judgments keyed by (question_id, judge_model) for --resume."""
    if not path or not path.exists():
        return {}
    raw = json.loads(path.read_text())
    out: dict[tuple[str, str], JudgmentResult] = {}
    for j in raw.get("judgments", []):
        out[(j["question_id"], j["judge_model"])] = JudgmentResult(
            question_id=j["question_id"],
            tier=j.get("tier", ""),
            bias=j.get("bias", ""),
            judge_model=j["judge_model"],
            blinding=j.get("blinding", {}),
            rag_scores=j.get("rag_scores") or {},
            wiki_scores=j.get("wiki_scores") or {},
            notes=j.get("notes", ""),
            raw_response=j.get("raw_response", ""),
            error=j.get("error"),
        )
    return out


async def run_async(spec: RunSpec) -> int:
    rubric = load_rubric(spec.rubric_path)
    rag_run = load_run(spec.rag_run)
    wiki_run = load_run(spec.wiki_run)
    pairs = pair_runs(rag_run, wiki_run)

    if not pairs:
        err("no overlapping questions between the two runs; nothing to judge")
        return 1

    if spec.max_questions:
        pairs = pairs[: spec.max_questions]

    info(
        f"rubric:        {spec.rubric_path}\n"
        f"rag run:       {spec.rag_run}\n"
        f"wiki run:      {spec.wiki_run}\n"
        f"judge:         {spec.judge_model} (effort={spec.reasoning_effort})\n"
        f"questions:     {len(pairs)}\n"
        f"criteria:      {', '.join(rubric.ids)}"
    )

    if spec.dry_run:
        info("\nDry run — would judge:")
        rng = random.Random(spec.seed)
        for p in pairs:
            blinding = blind(rng, p.id)
            info(f"  {p.id:35s} A={blinding['A']:5s} B={blinding['B']:5s} tier={p.tier}")
        return 0

    rng = random.Random(spec.seed)
    primary_done = existing_judgments(spec.resume_path)

    judgments: list[JudgmentResult] = []
    for p in pairs:
        blinding = blind(rng, p.id)
        cached = primary_done.get((p.id, spec.judge_model))
        if cached:
            info(f"resume {p.id} — already scored")
            judgments.append(cached)
            continue
        info(f"judge  {p.id} tier={p.tier} A={blinding['A']} B={blinding['B']}")
        result = await judge_one(
            p, rubric, blinding, spec.judge_model, spec.reasoning_effort
        )
        if result.error:
            info(f"  -> error: {result.error}")
        else:
            info(
                "  -> rag={"
                + ", ".join(f"{k}:{v}" for k, v in result.rag_scores.items())
                + "}  wiki={"
                + ", ".join(f"{k}:{v}" for k, v in result.wiki_scores.items())
                + "}"
            )
        judgments.append(result)

    secondary: list[JudgmentResult] = []
    if spec.secondary_judge and spec.secondary_judge_questions:
        secondary_targets = [
            p for p in pairs if p.id in spec.secondary_judge_questions
        ]
        info(
            f"\nsecondary judge: {spec.secondary_judge} on "
            f"{len(secondary_targets)} question(s)"
        )
        rng2 = random.Random(spec.seed + 1)  # different blinding for the second judge
        for p in secondary_targets:
            blinding = blind(rng2, p.id)
            info(f"judge2 {p.id} tier={p.tier} A={blinding['A']} B={blinding['B']}")
            result = await judge_one(
                p, rubric, blinding, spec.secondary_judge, spec.reasoning_effort
            )
            secondary.append(result)

    payload = {
        "judged_at": utc_timestamp(),
        "rag_run": str(spec.rag_run),
        "wiki_run": str(spec.wiki_run),
        "rubric": str(spec.rubric_path),
        "judge_model": spec.judge_model,
        "reasoning_effort": spec.reasoning_effort,
        "seed": spec.seed,
        "criteria": [c.id for c in rubric.criteria],
        "judgments": [_judgment_to_dict(j) for j in judgments],
        "aggregate": aggregate(judgments, rubric.ids),
        "secondary": (
            {
                "judge_model": spec.secondary_judge,
                "judgments": [_judgment_to_dict(j) for j in secondary],
                "agreement": _inter_rater_deltas(judgments, secondary, rubric.ids),
            }
            if secondary
            else None
        ),
    }
    out = spec.results_dir / f"judged-{utc_timestamp()}.json"
    write_json(out, payload)
    info(f"\nwrote judgments -> {out}")
    return 0


def _judgment_to_dict(j: JudgmentResult) -> dict:
    return {
        "question_id": j.question_id,
        "tier": j.tier,
        "bias": j.bias,
        "judge_model": j.judge_model,
        "blinding": j.blinding,
        "rag_scores": j.rag_scores,
        "wiki_scores": j.wiki_scores,
        "notes": j.notes,
        "raw_response": j.raw_response,
        "error": j.error,
    }


def _inter_rater_deltas(
    primary: list[JudgmentResult],
    secondary: list[JudgmentResult],
    criterion_ids: list[str],
) -> dict:
    """For overlapping question_ids, compute |primary - secondary| per criterion."""
    primary_by_id = {j.question_id: j for j in primary}
    out: dict = {"per_question": [], "max_deltas": {cid: 0 for cid in criterion_ids}}
    for s in secondary:
        p = primary_by_id.get(s.question_id)
        if not p:
            continue
        deltas: dict[str, dict[str, int | None]] = {}
        for cid in criterion_ids:
            for system in ("rag", "wiki"):
                pv = (p.rag_scores if system == "rag" else p.wiki_scores).get(cid)
                sv = (s.rag_scores if system == "rag" else s.wiki_scores).get(cid)
                if pv is not None and sv is not None:
                    delta = abs(int(pv) - int(sv))
                    deltas.setdefault(cid, {})[system] = delta
                    out["max_deltas"][cid] = max(out["max_deltas"][cid], delta)
        out["per_question"].append({"question_id": s.question_id, "deltas": deltas})
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rag-run", required=True, type=Path,
                   help="path to RAG run-<ts>.json")
    p.add_argument("--wiki-run", required=True, type=Path,
                   help="path to Wiki run-<ts>.json (matching schema)")
    p.add_argument("--rubric", required=True, type=Path,
                   help="path to rubric.yaml")
    p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                   help=f"primary judge model (default: {DEFAULT_JUDGE_MODEL})")
    p.add_argument("--reasoning-effort", default=DEFAULT_REASONING_EFFORT,
                   help=f"reasoning effort for the judge (default: {DEFAULT_REASONING_EFFORT})")
    p.add_argument("--secondary-judge", default=None,
                   help="optional second judge model for inter-rater reliability")
    p.add_argument("--secondary-judge-questions", default="",
                   help="comma-separated question ids to re-judge with the secondary model")
    p.add_argument("--seed", type=int, default=42,
                   help="random seed for blinding (default: 42)")
    p.add_argument("--max-questions", type=int, default=None,
                   help="cap the number of questions judged (for cost-bounded smoke runs)")
    p.add_argument("--resume", type=Path, default=None,
                   help="path to a prior judged-*.json; skips question_ids already scored by the same judge")
    p.add_argument("--results-dir", type=Path, default=Path(DEFAULT_RESULTS_DIR),
                   help=f"where to write judged-<ts>.json (default: {DEFAULT_RESULTS_DIR})")
    p.add_argument("--dry-run", action="store_true",
                   help="print what would be judged without calling the LLM")
    return p


def parse_args(argv: list[str] | None = None) -> RunSpec:
    args = build_parser().parse_args(argv)
    secondary_qs = {
        q.strip() for q in (args.secondary_judge_questions or "").split(",") if q.strip()
    }
    return RunSpec(
        rag_run=args.rag_run,
        wiki_run=args.wiki_run,
        rubric_path=args.rubric,
        judge_model=args.judge_model,
        reasoning_effort=args.reasoning_effort,
        secondary_judge=args.secondary_judge,
        secondary_judge_questions=secondary_qs,
        seed=args.seed,
        max_questions=args.max_questions,
        resume_path=args.resume,
        dry_run=args.dry_run,
        results_dir=args.results_dir,
    )


def main(argv: list[str] | None = None) -> int:
    spec = parse_args(argv)
    return asyncio.run(run_async(spec))


if __name__ == "__main__":
    sys.exit(main())
