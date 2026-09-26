#!/usr/bin/env python3
"""Rescore the claim-level grounding with the passage cap removed (post-hoc).

run_claim_grounding.py cut every cited passage to its first 1,500 characters
before the scorer saw it (``truncate(c, 1500)`` in ``call_openai_score``), and
run_claim_grounding_decomp.py imports the same scorer. RAG chunks run to about
2,500 characters and wiki excerpts to about 430, so the cap cut 128 of the 132
cited RAG claims, 200 of the 219 cited decomp claims, and none of the 241 cited
wiki claims.

This script re-runs the scoring stage only. It reads the atomized claims from
the deposited grounding artifacts instead of re-atomizing, so every claim, its
citations and its claim_idx are the ones originally scored, and the ones the
human-validation sample was drawn from. The scorer's system prompt and model
name are read out of run_claim_grounding.py's source rather than copied here,
so they cannot drift from the original.

    --cap none   score against the full cited passages (the correction)
    --cap 1500   rebuild the original request byte for byte; run it on rag as
                 the rerun-noise control, since scorer reruns are not
                 deterministic

Dry run by default: checks every input against ARTIFACTS_MANIFEST.txt, checks
every claim against the original scored row, and prints the plan. Nothing is
sent to the API without --run. Needs only OPENAI_API_KEY, read from .env, and a
Python with openai and python-dotenv installed (backend/.venv has both).

Usage:
    python experiments/rescore_claim_grounding.py --arm main
    python experiments/rescore_claim_grounding.py --arm main --run
    python experiments/rescore_claim_grounding.py --arm main --cap 1500 --systems rag --run
    python experiments/rescore_claim_grounding.py --arm decomp --run

Output: experiments/results/post-hoc/rescore-<arm>-cap<cap>[-<systems>]-<ts>.json.
A checkpoint beside it (rescore-<...>.partial.jsonl) lets an interrupted run
resume where it stopped; it is removed once the output is written.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
SOURCE_SCRIPT = ROOT / "experiments" / "run_claim_grounding.py"
MANIFEST = RESULTS / "ARTIFACTS_MANIFEST.txt"

ARMS = {
    "main": {
        "grounding": "post-hoc/grounding-20260508T155234Z.json",
        "runs": {"rag": "run-20260506T221602Z.json",
                 "wiki": "wiki-run-20260506T205500Z.json"},
        "systems": ("rag", "wiki"),
    },
    "decomp": {
        # The decomp artifact carries its own sources inside "atomized".
        "grounding": "post-hoc/grounding-decomp-20260509T021528Z.json",
        "runs": {},
        "systems": ("decomp",),
    },
}

ORIGINAL_CAP = 1500
VERDICTS = ("supported", "partial", "contradicted", "unsupported")

# Errors no retry can fix. They stop the run at once instead of being retried
# on every remaining item.
FATAL = {"AuthenticationError", "PermissionDeniedError", "NotFoundError",
         "BadRequestError"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest_hashes() -> dict[str, str]:
    """{published name: sha256} from ARTIFACTS_MANIFEST.txt."""
    if not MANIFEST.exists():
        raise SystemExit(f"{MANIFEST} not found; it ships with the OSF deposit")
    out, name = {}, None
    for line in MANIFEST.read_text().splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
        elif name and line.strip().startswith("sha256:"):
            out[name] = line.split(":", 1)[1].strip()
    return out


def verify_inputs(arm: str) -> dict[str, str]:
    """Hash every input and stop unless it matches the deposit manifest."""
    spec = ARMS[arm]
    expected = manifest_hashes()
    got = {}
    for name in [spec["grounding"], *spec["runs"].values()]:
        path = RESULTS / name
        if not path.exists():
            raise SystemExit(f"missing input {path}")
        digest = sha256(path)
        if expected.get(name) != digest:
            raise SystemExit(f"{name}: sha256 {digest} does not match the"
                             f" manifest ({expected.get(name, 'not listed')})")
        got[name] = digest
    return got


def original_scorer() -> tuple[str, str]:
    """SCORE_SYSTEM and SCORER_MODEL, read from the original script's source.

    Parsed rather than imported: importing run_claim_grounding builds an
    Anthropic client at module level and fails without ANTHROPIC_API_KEY,
    which scoring does not need.
    """
    found = {}
    for node in ast.parse(SOURCE_SCRIPT.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (isinstance(target, ast.Name)
                    and target.id in ("SCORE_SYSTEM", "SCORER_MODEL")):
                found[target.id] = ast.literal_eval(node.value)
    missing = {"SCORE_SYSTEM", "SCORER_MODEL"} - set(found)
    if missing:
        raise SystemExit(f"{SOURCE_SCRIPT.name}: no {', '.join(sorted(missing))}")
    return found["SCORE_SYSTEM"], found["SCORER_MODEL"]


def truncate(text: str, n: int | None) -> str:
    """run_claim_grounding.truncate, where None means no cap."""
    if n is None or len(text) <= n:
        return text
    return text[:n] + "..."


def build_user(claim: str, chunks: list[str], cap: int | None) -> str:
    """The scorer's user message, built exactly as call_openai_score builds it."""
    passages = "\n\n".join(f"--- passage {i} ---\n{truncate(c, cap)}"
                           for i, c in enumerate(chunks))
    return f"CLAIM:\n{claim}\n\nCITED PASSAGES:\n{passages}"


def cited_chunks(sources: list[dict], idx: list[int]) -> list[str]:
    """Valid, non-empty cited chunks, collected as score_all collects them."""
    out = []
    for i in idx:
        if 0 <= i < len(sources):
            ct = sources[i].get("chunk_text", "")
            if ct:
                out.append(ct)
    return out


def key(item: dict) -> str:
    return f"{item['system']}|{item['qid']}|{item['claim_idx']}"


def load_items(arm: str) -> list[dict]:
    """Every scored row of the arm, joined back to its claim and passages.

    Stops on any disagreement between the atomized claims and the scored rows,
    since that would mean rescoring something other than what was scored.
    """
    spec = ARMS[arm]
    g = json.loads((RESULTS / spec["grounding"]).read_text())

    if arm == "decomp":
        by_qid = {q["qid"]: q for q in g["atomized"]}
        n_atomized = sum(len(q["claims"]) for q in g["atomized"])

        def lookup(row):
            q = by_qid[row["qid"]]
            return q["claims"], q["sources"], q["tier"]
    else:
        runs = {s: {r["id"]: r for r in
                    json.loads((RESULTS / f).read_text())["results"]}
                for s, f in spec["runs"].items()}
        n_atomized = sum(len(s["claims"]) for q in g["atomized"].values()
                         for s in q.values())

        def lookup(row):
            run = runs[row["system"]][row["qid"]]
            claims = g["atomized"][row["qid"]][row["system"]]["claims"]
            return claims, run["sources"], run["tier"]

    if len(g["scored"]) != n_atomized:
        raise SystemExit(f"{spec['grounding']}: {len(g['scored'])} scored rows"
                         f" for {n_atomized} atomized claims")

    items = []
    for row in g["scored"]:
        claims, sources, tier = lookup(row)
        claim = claims[row["claim_idx"]]
        idx = claim.get("cited_source_idx", [])
        chunks = cited_chunks(sources, idx)
        where = f"{row['system']} {row['qid']} #{row['claim_idx']}"
        if claim["claim"] != row["claim"] or idx != row["cited_source_idx"]:
            raise SystemExit(f"{where}: atomized claim differs from scored row")
        if len(chunks) != row["n_cited_chunks"]:
            raise SystemExit(f"{where}: {len(chunks)} cited chunks, artifact"
                             f" says {row['n_cited_chunks']}")
        items.append({
            "qid": row["qid"],
            "system": row["system"],
            "tier": tier,
            "claim_idx": row["claim_idx"],
            "claim": row["claim"],
            "cited_source_idx": idx,
            "n_cited_chunks": len(chunks),
            "passage_chars": [len(c) for c in chunks],
            "cut_by_original_cap": any(len(c) > ORIGINAL_CAP for c in chunks),
            "original_verdict": row["verdict"],
            "original_reason": row["reason"],
            "_chunks": chunks,
        })
    if len({key(it) for it in items}) != len(items):
        raise SystemExit(f"{spec['grounding']}: duplicate (system, qid, claim_idx)")
    return items


def make_client():
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(f"OPENAI_API_KEY is not set; add it to {ROOT / '.env'}")
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def score_one(client, system_prompt: str, model: str, item: dict,
              cap: int | None, max_retries: int = 3) -> dict:
    """One scorer call, with call_openai_score's parameters and fallback."""
    user = build_user(item["claim"], item["_chunks"], cap)
    last = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user}],
                reasoning_effort="medium",
                response_format={"type": "json_object"},
            )
            obj = json.loads(resp.choices[0].message.content)
            break
        except Exception as e:
            if type(e).__name__ in FATAL:
                raise
            last = e
            sleep = 2 ** attempt
            print(f"  [retry {attempt + 1}/{max_retries} after {sleep}s]"
                  f" {key(item)} {type(e).__name__}: {str(e)[:120]}",
                  file=sys.stderr)
            time.sleep(sleep)
    else:
        raise last
    raw = obj.get("verdict")
    usage = getattr(resp, "usage", None)
    return {
        # The original maps an out-of-vocabulary verdict to unsupported; keep
        # that, and keep what the model actually said beside it.
        "verdict": raw if raw in VERDICTS else "unsupported",
        "verdict_raw": raw,
        "reason": obj.get("reason", ""),
        "served_model": resp.model,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def load_checkpoint(path: Path, config: dict) -> tuple[dict, str | None]:
    """Results already on disk for this exact configuration."""
    if not path.exists():
        return {}, None
    lines = path.read_text().splitlines()
    header = json.loads(lines[0]) if lines else {}
    if header.get("config") != config:
        raise SystemExit(f"{path.name} was written under a different"
                         " configuration; move it aside to start over")
    done = {}
    for line in lines[1:]:
        if line.strip():
            rec = json.loads(line)
            done[rec["key"]] = rec["result"]
    return done, header.get("started_at")


def summarize(rows: list[dict]) -> dict:
    """Cited-claim verdicts per system, before and after, overall and by tier."""
    out = {}
    for system in sorted({r["system"] for r in rows}):
        cited = [r for r in rows
                 if r["system"] == system and r["n_cited_chunks"] > 0]
        by_tier = {}
        for tier in sorted({r["tier"] for r in cited}):
            t = [r for r in cited if r["tier"] == tier]
            by_tier[tier] = {
                "n_cited": len(t),
                "original": dict(Counter(r["original_verdict"] for r in t)),
                "rescored": dict(Counter(r["verdict"] for r in t)),
            }
        old = Counter(r["original_verdict"] for r in cited)
        new = Counter(r["verdict"] for r in cited)
        moved = Counter(f"{r['original_verdict']}->{r['verdict']}"
                        for r in cited if r["verdict"] != r["original_verdict"])
        out[system] = {
            "n_cited": len(cited),
            "n_cut_by_original_cap": sum(r["cut_by_original_cap"] for r in cited),
            "n_unchanged": sum(r["verdict"] == r["original_verdict"] for r in cited),
            "original": {v: old[v] for v in VERDICTS},
            "rescored": {v: new[v] for v in VERDICTS},
            "transitions": dict(sorted(moved.items())),
            "by_tier": by_tier,
        }
    return out


def print_summary(summary: dict) -> None:
    for system, s in summary.items():
        n = s["n_cited"]
        print(f"\n  {system}: {n} cited claims, {s['n_cut_by_original_cap']} cut"
              f" by the original cap, {s['n_unchanged']} verdicts unchanged")
        print(f"    {'verdict':<14}{'original':>14}{'rescored':>14}")
        for v in VERDICTS:
            a, b = s["original"][v], s["rescored"][v]
            print(f"    {v:<14}{a:>5} {a / n:6.1%} {b:>6} {b / n:6.1%}")
        if s["transitions"]:
            print("    moved: " + ", ".join(f"{k} {v}"
                                         for k, v in s["transitions"].items()))


def parse_cap(value: str) -> int | None:
    if value.lower() == "none":
        return None
    cap = int(value)
    if cap <= 0:
        raise argparse.ArgumentTypeError("cap must be positive, or none")
    return cap


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=sorted(ARMS), required=True)
    ap.add_argument("--cap", type=parse_cap, default=None,
                    help="characters kept per passage, or none (default: none)")
    ap.add_argument("--systems", default=None,
                    help="comma-separated subset of the arm's systems")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-dir", type=Path, default=RESULTS / "post-hoc")
    ap.add_argument("--run", action="store_true",
                    help="call the scorer; without it, verify and plan only")
    args = ap.parse_args(argv)

    arm_systems = ARMS[args.arm]["systems"]
    requested = ({s.strip() for s in args.systems.split(",")}
                 if args.systems else set(arm_systems))
    unknown = requested - set(arm_systems)
    if unknown:
        raise SystemExit(f"--systems: {', '.join(sorted(unknown))} not in arm"
                         f" {args.arm} ({', '.join(arm_systems)})")
    systems = tuple(s for s in arm_systems if s in requested)

    inputs = verify_inputs(args.arm)
    system_prompt, model = original_scorer()
    items = [it for it in load_items(args.arm) if it["system"] in systems]
    todo = [it for it in items if it["n_cited_chunks"] > 0]

    cap_label = "none" if args.cap is None else str(args.cap)
    tag = f"{args.arm}-cap{cap_label}"
    if systems != arm_systems:
        tag += "-" + "-".join(systems)
    config = {
        "arm": args.arm,
        "cap": args.cap,
        "systems": list(systems),
        "scorer_model": model,
        "score_system_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "inputs": inputs,
    }

    print(f"arm {args.arm}, cap {cap_label}, systems {', '.join(systems)}")
    print("inputs match ARTIFACTS_MANIFEST.txt:")
    for name, digest in inputs.items():
        print(f"  {name}  {digest[:16]}")
    print(f"scorer {model}, prompt read from {SOURCE_SCRIPT.name}"
          f" (sha256 {config['score_system_sha256'][:16]})")
    print("every claim matches its original scored row")
    for system in systems:
        rows = [it for it in items if it["system"] == system]
        cited = [it for it in rows if it["n_cited_chunks"] > 0]
        cut = sum(it["cut_by_original_cap"] for it in cited)
        print(f"  {system:<7} {len(rows)} claims: {len(cited)} cited to score"
              f" ({cut} cut by the original cap), {len(rows) - len(cited)}"
              " uncited carried over unchanged")
    if args.cap == ORIGINAL_CAP:
        print(f"cap {ORIGINAL_CAP} rebuilds the original requests exactly:"
              " a rerun-noise control, not a correction")
    print(f"{len(todo)} scorer calls")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = args.out_dir / f"rescore-{tag}.partial.jsonl"
    done, started_at = load_checkpoint(ckpt, config)
    if done:
        print(f"checkpoint {ckpt.name}: {len(done)} already scored, resuming")

    if not args.run:
        print("\ndry run: nothing sent. Add --run to score.")
        return

    client = make_client()
    started_at = started_at or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not ckpt.exists():
        ckpt.write_text(json.dumps({"config": config, "started_at": started_at}) + "\n")
    lock = threading.Lock()

    def record(item, result):
        with lock:
            done[key(item)] = result
            with ckpt.open("a") as fh:
                fh.write(json.dumps({"key": key(item), "result": result}) + "\n")

    pending = [it for it in todo if key(it) not in done]
    total = len(todo)
    try:
        # One call on its own first, so a retired model or a bad key stops the
        # run after a single request, and so the served model is checked
        # before the rest go out.
        if pending:
            first = pending.pop(0)
            result = score_one(client, system_prompt, model, first, args.cap)
            if not result["served_model"].startswith(model):
                raise SystemExit(f"asked for {model}, served"
                                 f" {result['served_model']}; stopping before"
                                 " anything is recorded")
            print(f"served model {result['served_model']}")
            record(first, result)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(score_one, client, system_prompt, model, it,
                                   args.cap): it for it in pending}
            try:
                for fut in as_completed(futures):
                    record(futures[fut], fut.result())
                    if len(done) % 25 == 0 or len(done) == total:
                        print(f"[score {len(done)}/{total}]", flush=True)
            except BaseException:
                pool.shutdown(wait=True, cancel_futures=True)
                raise
    except BaseException as e:
        print(f"stopped with {len(done)}/{total} scored; the same command"
              f" resumes from {ckpt.name}", file=sys.stderr)
        if type(e).__name__ in FATAL:
            raise SystemExit(f"{type(e).__name__}: {str(e)[:300]}") from None
        raise

    rows = []
    for it in items:
        row = {k: v for k, v in it.items() if not k.startswith("_")}
        if it["n_cited_chunks"] > 0:
            row.update(done[key(it)], rescored=True)
        else:
            row.update(verdict=it["original_verdict"],
                       reason=it["original_reason"], rescored=False)
        rows.append(row)

    summary = summarize(rows)
    finished_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"rescore-{tag}-{finished_at}.json"
    out_path.write_text(json.dumps({
        "kind": "claim-grounding-rescore",
        "post_hoc": True,
        **config,
        "original_cap": ORIGINAL_CAP,
        "reasoning_effort": "medium",
        "served_models": sorted({done[key(it)]["served_model"] for it in todo}),
        "source_script": "experiments/run_claim_grounding.py",
        "source_script_sha256": sha256(SOURCE_SCRIPT),
        "rescore_script_sha256": sha256(Path(__file__)),
        "started_at": started_at,
        "finished_at": finished_at,
        "summary": summary,
        "rows": rows,
    }, indent=2))
    ckpt.unlink()

    print_summary(summary)
    print(f"\n[saved {out_path}]")


if __name__ == "__main__":
    main()
