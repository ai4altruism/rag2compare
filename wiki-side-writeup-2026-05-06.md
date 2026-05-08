# Wiki-Side Contribution to the rag2compare Write-Up — 2026-05-06

> **Scope.** Wiki side only. The cross-family judging happens externally in the `rag2compare` repo against both this artifact set and the RAG side; H1/H2/H3 verdicts depend on judged scores which are not yet available. Anything cross-family is marked **PENDING**.
>
> **Audience.** A downstream session writing the comprehensive RAG-vs-Wiki report. Treat this document as a vetted source: every load-bearing claim points to a file path or a `jq` query you can re-run against the artifacts on `main`. Special emphasis (per the user's request) on **how the Anthropic API was used and how that shaped the token totals** — that is §4–§5 below.

---

## 1. What ran, where it lives

Two formal artifacts on `main` (commit `c8fdddc`, merged via PR #9 / merge `8dbf418`):

| File | Bytes | What it is |
|---|---|---|
| `experiments/results/wiki-run-20260506T205500Z.json` | ~190 KB | The 13 evaluation answers + per-question token/latency metadata. The artifact the cross-family judge reads. |
| `experiments/results/wiki-ingest-20260506T211731Z.json` | ~14 KB | Per-paper ingest stopwatch + session-level token totals. Drives the H3 cost-crossover analysis. |

Three iterations of smoke output and an earlier ingest sanity-check are on disk locally but `.gitignore`d (covered in §7):

```
experiments/results/wiki-ingest-20260506T204023Z.json     # pre-formal ingest snapshot
experiments/results/wiki-run-smoke-20260506T204135Z.json  # smoke #1 — thinking capture broken
experiments/results/wiki-run-smoke-20260506T204641Z.json  # smoke #2 — hallucinated PDFs surfaced
experiments/results/wiki-run-smoke-20260506T205038Z.json  # smoke #3 — clean
experiments/results/run_wiki_full.log                     # 209-line per-turn trace of formal run
```

The harness, runners, and runbook live under `experiments/`:

```
experiments/
  harness.py        # tool-loop, system prompt, post-filter, token accounting
  run_wiki.py       # iterates the 13 questions, writes wiki-run-<ts>.json
  run_ingest.py     # one-shot deterministic transform from build-cost stopwatch table
  README.md         # operator runbook
  .env              # ANTHROPIC_API_KEY (gitignored)
```

The contract the harness implements is `WIKI_SIDE_BRIEF.md` at the repo root (12 KB; the cross-family judge silently zero-fills missing fields, so the schema is load-bearing).

---

## 2. The experiment in one paragraph

Two knowledge architectures (LLM-built wiki vs traditional chunked RAG) over a fixed 24-paper corpus across three domains (`ai-ethics-law`, `climate-science`, `precision-medicine`), answered by a single fixed model — **Claude Opus 4.7 at `xhigh` adaptive thinking** — against 13 prescribed questions: ten written to favour wiki synthesis (Tiers 1–5, two each) and three "bias-check" point-source questions written to favour RAG (B1/B2/B3). Hypotheses: **H1** wiki beats RAG on multi-hop synthesis; **H2** RAG matches/beats wiki on point-source retrieval; **H3** the cost curves cross — wiki front-loads spend at ingest, RAG amortizes per-query. The full corpus list, question text, output schema, and validation jq queries are all fixed verbatim in `WIKI_SIDE_BRIEF.md` §3, §4, §7, §8.

---

## 3. The wiki under test

The wiki was built before the experiment, on `main` ahead of the run. Pointers:

- Build-cost analysis: `wiki/analyses/build-cost-2026-05-06.md` — 24 papers, 25,379 s of per-paper stopwatch (7.05 h), 8 h 19 m of JSONL ≤2-min active, 25 h 34 m wall-clock, 904.8M total tokens (898.6M in / 6.3M out). This is the canonical ingest cost number; the wiki-side ingest artifact is a deterministic transform of this table.
- Page count + structure: `wiki/index.md` (top of file lists all sources/concepts/entities/analyses; reproducible via `find wiki -name '*.md' | wc -l`).
- Schema: `CLAUDE.md` (frontmatter format, file-naming, cross-reference style).

The wiki was not modified between build completion and the formal run.

---

## 4. The query harness — model, tools, control flow

`experiments/harness.py:1-437`. The shape of every claim about token totals in §5–§6 traces back here.

### 4.1 Model configuration

`harness.py:34-39`:

```python
MODEL = "claude-opus-4-7"
EFFORT = "xhigh"
MAX_TOKENS = 16000
MAX_TURNS = 30
MAX_PAGES_READ = 60
PER_QUESTION_TIMEOUT_S = 30 * 60
PER_CALL_TIMEOUT_S = 600
```

The brief (`WIKI_SIDE_BRIEF.md` §5.1–5.2) prescribes the request shape verbatim, including three anti-footguns the RAG side learned the hard way:

- `thinking={"type": "adaptive", "display": "summarized"}` — Opus 4.7 rejects the legacy `{"type":"enabled","budget_tokens":N}` shape with HTTP 400. Adaptive is the only supported form.
- `display: "summarized"` is required, not just nice-to-have. The default `"omitted"` suppresses thinking blocks **and** zeroes `reasoning_tokens` even when thinking actually ran. With `summarized`, the assistant message contains structured `thinking` content blocks the harness can post-process for the H3 token-cost analysis.
- No `temperature`, no `top_p`, no `top_k` — Opus 4.7 returns HTTP 400 (`temperature is deprecated for this model`) if any are sent.

`output_config={"effort": "xhigh"}` is soft guidance for thinking allocation. It does not override the per-call `max_tokens` ceiling.

### 4.2 Tools and the agentic loop

Three tools, definitions at `harness.py:169-226`:

| Tool | Effect |
|---|---|
| `list_pages(directory)` | Lists `.md` filenames in `wiki/<directory>` (one of `""`, `sources`, `entities`, `concepts`, `analyses`). Sandboxed via `_safe_resolve` (`harness.py:130-137`). |
| `read_page(path)` | Reads a `.md` file under `wiki/`. Hard-truncated at 100 000 chars (`harness.py:163-166`). Increments a per-question `pages_read` set used to enforce `MAX_PAGES_READ`. |
| `submit_answer({answer, sources})` | Terminates the loop. The `sources` array is the H1/H2 grounding evidence the cross-family judge will score. |

Loop body at `harness.py:281-358`:

1. POST `messages.create` with the running `messages` list (system prompt + initial user question + every prior `(assistant_response, tool_results)` pair so far).
2. Increment `prompt_tokens += usage.input_tokens`, `completion_tokens += usage.output_tokens`, and (separately, see §4.4) `thinking_tokens`.
3. Append the **full assistant response** (including thinking blocks with their cryptographic signatures) to `messages` — required for thinking-block continuity across turns.
4. For each `tool_use` block in the response, run the local handler and append a matching `tool_result` block to `messages` as a single `user`-role message.
5. Stop when `submit_answer` is called, or when `stop_reason == "end_turn"`, or after `MAX_TURNS = 30` (in which case the harness forces a final turn with `tool_choice={"type":"tool","name":"submit_answer"}` per `harness.py:287-298`).

> **NOTE for the report writer.** Although the model nominally has 30 turns, **no question used more than 8** (B3-mia-attack-success-rate, the most expensive bias-check). The forced-submit fallback never triggered. See the per-question turn distribution in §5.4.

### 4.3 No prompt caching

The harness does **not** use Anthropic prompt caching. Specifically:

- The system prompt (`harness.py:76-127`, ~3 200 chars) is sent verbatim every turn with no `cache_control` markers.
- The tool definitions (~1 600 chars) are sent verbatim every turn.
- Wiki page contents read via `read_page` are reflected back to the model as `tool_result` blocks; those `tool_result`s are not cache-anchored either.

This is a deliberate simplification but it has direct token-cost consequences for §6's H3 analysis: every prompt token reported in `wiki-run-20260506T205500Z.json` is a billable uncached input token at full Opus 4.7 input rate. If the report writer wants to compare against a hypothetical caching-enabled wiki harness, the upper-bound savings are roughly (system prompt + tool defs) × turns_after_first × hit_rate, which on the formal run would have been on the order of 60–100k input tokens out of 1.55M — meaningful but not order-of-magnitude. The dominant cost driver is the accumulating tool-result history, which §4.5 explains.

### 4.4 The `count_tokens` workaround for thinking-token capture

`harness.py:229-255` (`_count_thinking_tokens`). The brief says (`WIKI_SIDE_BRIEF.md` §5.4) to capture per-call thinking tokens; the obvious approach — `count_tokens(full_response) − count_tokens(response_minus_thinking)` — does not work, because:

> The Anthropic `count_tokens` endpoint rejects an assistant message that ends in or contains an unmatched `tool_use` block with HTTP 400 ("`tool_use` ids were found without `tool_result` blocks immediately after"). On every tool-using turn (which is most of them), the assistant response ends in a `tool_use`, so neither the full nor the stripped form passes the validator.

The workaround is to count, per turn, only each `thinking` block's `.thinking` text individually as a synthetic `user` message and sum across blocks:

```python
for b in content_blocks:
    if b.type != "thinking" or not b.thinking:
        continue
    ct = client.messages.count_tokens(model=MODEL,
                                       messages=[{"role": "user", "content": b.thinking}])
    total += ct.input_tokens
```

Caveats the report writer should know:

- This **slightly over-counts** because each block is wrapped in user-message overhead (~5–10 tokens per block). A 1 461-token result for T2-oae-bio-vs-chemical is more like 1 430-ish actual thinking tokens. The over-count is bounded and uniform.
- It correctly orders zero vs. non-zero thinking, which is what H3 needs (per `WIKI_SIDE_BRIEF.md` §5.3, "a zero `thinking_tokens` count is not a bug — record it honestly").
- On `count_tokens` failure (rate-limit, network, etc.) the function returns 0 and prints a warning. Across the formal run there are zero such failures in `run_wiki_full.log`.
- The brief's `WIKI_SIDE_BRIEF.md` §5.4 examples assume LiteLLM's normalized `usage.completion_tokens_details.reasoning_tokens` field. The Anthropic SDK does not expose that; the workaround replaces it.

### 4.5 Why prompt tokens grow non-trivially across turns

The agentic loop appends every prior `(assistant_response, tool_results)` pair to `messages` before the next call. With no caching, each turn re-bills the entire growing prefix as input tokens. Concretely, from the per-turn log for T1-cardio-baselines (`run_wiki_full.log` lines for question 1):

| Turn | `usage.input_tokens` | What was new in the prefix |
|---|---|---|
| 1 | 3 582 | system + tool defs + initial user question |
| 2 | 41 440 | + turn 1 assistant response + two tool results (`index.md` 79 729 chars, `list_pages('sources')` 2 858 chars) |
| 3 | 70 430 | + turn 2 assistant response + two tool results (~33 KB + ~40 KB pages) |

`prompt_tokens` for the question = 3 582 + 41 440 + 70 430 = 115 452 — exactly what `metadata.prompt_tokens` reports. The 79 729-char `index.md` page alone, charged twice (once on turn 2 as the result, once on turn 3 as part of the prefix), accounts for roughly 40k of those tokens.

**Implication for H3.** The wiki-side per-question prompt token count is dominated by the tool-result echo of the wiki pages the model chose to read, multiplied by however many turns elapsed after each read. RAG's retrieved-context-once-per-query pattern doesn't have this growth term. This is the single most important shape-of-cost fact for the H3 write-up: wiki query cost is not just "the wiki page sizes" — it's "wiki page sizes × turn-position weight".

### 4.6 The `CANONICAL_PDFS` post-filter

`harness.py:46-74` defines the 24-paper canonical PDF filename set. After `submit_answer`, the harness (`harness.py:362-388`):

1. Drops any source whose `filename` ends in `.pdf` and is **not** in `CANONICAL_PDFS`. This is the hallucination filter — the model occasionally invented domain-prefix variants like `ethics-chrono-devote3-pieber.pdf` for a precision-medicine paper (smoke #2 §7).
2. Dedupes remaining sources by `(filename, chunk_text)`.
3. Normalizes each source to the brief §7.1 schema, defaulting `page_numbers=[]` if absent.
4. Logs `[note] dropped N hallucinated PDF source entries` if any drops occurred.

Against the formal run, the `[note] dropped` line appears **zero times** in `run_wiki_full.log` — meaning the §3 prompt-side PDF table fix (described in §7) eliminated the bug at the source. The post-filter is now belt-and-braces.

---

## 5. The system prompt — what got into context every turn

`harness.py:76-127`. ~3 200 chars. Three structural sections that matter for understanding model behaviour and token cost:

1. **Tool descriptions** (lines 78-81). Repeats the API tool definitions in prose. Mostly redundant with the `tools` array but the model uses it as a how-to.
2. **Traversal instructions** (lines 83-86). "Start with `read_page('index.md')` or `overview.md`, follow `[[wiki-links]]`, then `submit_answer`." On the formal run, the model started from `index.md` on **12 of 13 questions**; the exception was T2-fair-use-vs-optin which jumped straight to `list_pages('sources')` then `list_pages('analyses')`. This is the question with the smallest `prompt_tokens` total (47 508) — see §6.1.
3. **The §3 PDF-filename table** (lines 88-118, ~1 700 chars). Embedded after the §2 hallucination incident in smoke #2. Lists all 24 canonical PDF filenames grouped by domain, with author/year/title parentheticals so the model can disambiguate. This is the upstream half of the §4.6 hallucination fix; the post-filter is the downstream half.
4. **Source-citation rules (LOAD-BEARING)** (lines 120-127). Instructs the model to include both wiki-page filenames and the canonical PDF filename for the same evidence (sibling source entries with `page_numbers=[]` and the same `chunk_text`). The cross-family judge needs the PDF filename for un-blinding.

The full prompt is sent verbatim every turn (no cache markers — see §4.3). On a 4-turn question that's ~13 000 tokens of system overhead alone.

---

## 6. Empirical results — the formal run

Source: `experiments/results/wiki-run-20260506T205500Z.json`. All 13 brief §8 jq validation checks pass; reproducible:

```bash
WIKI_RUN=experiments/results/wiki-run-20260506T205500Z.json
jq -r '.results[].id' "$WIKI_RUN" | sort | uniq -c           # 1 each of 13 ids
jq -r '.results[].metadata.model_used' "$WIKI_RUN" | sort -u # claude-opus-4-7
```

### 6.1 Per-question table

Generated by:

```bash
jq -r '.results[] | "\(.id)\t\(.tier)\t\(.bias)\t\(.metadata.prompt_tokens)\t\(.metadata.completion_tokens)\t\(.metadata.thinking_tokens)\t\(.metadata.latency_ms)"' \
  experiments/results/wiki-run-20260506T205500Z.json
```

| ID | Tier | Bias | prompt | completion | thinking | latency_ms | turns |
|---|---|---|---:|---:|---:|---:|---:|
| T1-cardio-baselines | chronological | neutral | 115 452 | 8 346 | 452 | 119 166 | 3 |
| T1-mia-evolution | chronological | neutral | 158 080 | 9 933 | 833 | 150 055 | 4 |
| T2-oae-bio-vs-chemical | conflict | wiki | 107 594 | 6 845 | 1 461 | 96 557 | 3 |
| T2-fair-use-vs-optin | conflict | wiki | **47 508** | 6 171 | 814 | 95 990 | 4 |
| T3-mia-as-copyright-evidence | multi-hop | wiki | 164 647 | 9 364 | 207 | 124 289 | 4 |
| T3-rwd-validity-for-side-effects | multi-hop | wiki | **204 290** | 8 505 | 665 | 129 110 | 4 |
| T4-eelgrass-mrv-gaps | emergence | wiki | 106 128 | 5 118 | 523 | 75 199 | 4 |
| T4-cross-domain-audit | emergence | wiki | 187 184 | 9 403 | 1 741 | 139 059 | 5 |
| T5-glp1-policy | policy | wiki | 133 466 | 9 175 | 169 | 128 962 | 4 |
| T5-25th-paper | policy | wiki | 163 987 | 7 254 | 1 486 | 139 073 | 5 |
| B1-devote3-confidence-interval | bias-check | rag | **27 453** | 1 993 | 177 | 26 254 | 3 |
| B2-he-tyka-equilibration-ratios | bias-check | rag | 28 353 | 2 641 | 178 | 39 735 | 3 |
| B3-mia-attack-success-rate | bias-check | rag | 110 080 | 3 014 | 667 | 53 733 | **8** |
| **Totals** | | | **1 552 222** | **87 762** | **9 373** | **1 317 282** | 54 |

(Turn counts grep'd from `run_wiki_full.log`; the per-question section terminates at `[done] turns=N`.)

Wall-clock total: 21 min 57 s (sum of latency_ms / 1000, then ÷ 60). This matches the 21.95 min figure in memory.

### 6.2 Headline observations the report writer should keep

1. **Adaptive thinking fired on every question.** No zeroes in the `thinking_tokens` column. Across the 13 questions thinking ranged 169–1 741 tokens. This is consistent with the brief §5.3 advisory that thinking is opportunistic — but the wiki-traversal task evidently triggers it consistently. Whether the RAG side gets the same coverage is a key thing for the cross-family report to compare; the brief flags it explicitly ("RAG-style synthesis prompts often score `thinking_tokens = 0`").
2. **Bias-check questions are 3–4× cheaper than synthesis on prompt tokens** (27 453 / 28 353 / 110 080 vs synthesis median ≈ 158 000) and 2–4× faster on wall-clock (26 254 / 39 735 / 53 733 ms vs synthesis median ≈ 124 289 ms). This is **directionally consistent with H2's cost-asymmetry claim** (wiki spends less on point-source lookups), but H2 is about *answer quality* relative to RAG, not just cost. The judged-score outcome is **PENDING** the cross-family judge.
3. **B3-mia-attack-success-rate is the bias-check outlier.** 8 turns, 110 080 prompt tokens — ~4× the cost of B1/B2. The trace (`run_wiki_full.log` lines for question 13) shows the model exploring multiple ethics-chrono pages looking for a CIFAR-10 success-rate number that the wiki summary apparently under-emphasized. Worth a sentence in the report: bias-check cost can spike when the wiki page didn't surface the exact number the question asks for, even though the underlying paper has it.
4. **T3-rwd-validity-for-side-effects is the most expensive question** (204 290 prompt tokens). Multi-hop, three papers (Sehgal Reddit data, Qiu RCT/RWD framework, Martinussen QoL truncation). Aligns with H1's claim that wiki excels on multi-hop synthesis — the cost reflects information density, not thrash.
5. **T2-fair-use-vs-optin is the cheapest non-bias-check question** (47 508). The model skipped `index.md`, jumped straight to `list_pages('sources')` and `list_pages('analyses')`, then read two source pages and submitted. This is the only question where the model deviated from the prompt's "start at index.md" instruction. The prompt prefix grew slowly because the listings are tiny (`list_pages('sources')` returns 2 858 chars). Worth flagging: the harness's per-question cost is sensitive to the model's traversal strategy in ways the prompt only weakly constrains.
6. **18 unique canonical PDFs cited across all 13 questions.** Six papers were never cited (Jones eelgrass, Nagwekar OAE modelling, Kupnicka GLP-1, Beheshti Parkinson's, McElhany lit-tag, +1) because no question asked about them. Verify with:

   ```bash
   jq -r '[.results[].sources[].filename | select(endswith(".pdf"))] | unique | length' \
     experiments/results/wiki-run-20260506T205500Z.json
   ```

7. **No turn-budget exhaustion, no error notes.**

   ```bash
   jq -r '.results[].metadata.error // "ok"' experiments/results/wiki-run-20260506T205500Z.json | sort -u
   # Expected: a single "ok"
   ```

### 6.3 Ingest artifact summary

`experiments/results/wiki-ingest-20260506T211731Z.json`. A deterministic transform of `wiki/analyses/build-cost-2026-05-06.md:88-115` (no API calls; see `experiments/run_ingest.py`).

| Metric | Value | Source |
|---|---|---|
| Documents | 24/24 complete | `wiki-ingest-...json` `.totals.documents`/`.completed` |
| Per-paper stopwatch total | 25 379 s = **7.05 h** | `.totals.total_seconds` |
| `tokens_in` (uncached + cache_creation + cache_read) | **898 594 660** | `.totals.tokens_in` |
| `tokens_out` | **6 290 000** | `.totals.tokens_out` |
| Combined total | **904.8M** | matches `wiki/analyses/build-cost-2026-05-06.md` headline |
| `by_domain.ai-ethics-law.total_seconds` | 5 856 s | `.totals.by_domain` |
| `by_domain.climate-science.total_seconds` | 9 382 s | |
| `by_domain.precision-medicine.total_seconds` | 10 141 s | |

Per-paper `tokens_in` / `tokens_out` are `null` per `WIKI_SIDE_BRIEF.md` §5.5: the wiki was built across multi-paper sessions with frequent context switches, and no per-paper boundary annotations exist in the session JSONLs. The brief explicitly permits null. Per-domain apportionment is approximate — see §7.3.

The relationship between the three time bases worth understanding for the H3 write-up:

- **Per-paper stopwatch (7.05 h)** = active manual-stopwatch time on each paper's ingest step, excludes lint passes and cross-arc operations.
- **JSONL ≤2-min active (8 h 19 m)** = derived from session JSONLs by counting any contiguous run of operations with gaps ≤120 s. Includes lint and overview-rewrite operations folded into the session.
- **Wall-clock (25 h 34 m)** = first-to-last operation across the entire build, including idle gaps.

The ingest artifact uses the per-paper stopwatch for per-document `ingestion_seconds` and the session-aggregated token count (which spans the full ≤2-min active envelope) for the totals. This is consistent and disclosed in `experiments/README.md:36-56`.

---

## 7. Procedural caveats — three things that bit during development

These are the load-bearing methodology footnotes for the report. Not curiosities — each one shaped the final numbers.

### 7.1 The `count_tokens`-on-`tool_use` API limitation

Already covered in §4.4. Recap for the report's "what we learned" section:

- **The bug.** `count_tokens` rejects assistant messages containing unmatched `tool_use` blocks. The intuitive diff-based approach (`count(full) − count(stripped)`) 400s every call.
- **The workaround.** Sum `count_tokens` over each `thinking` block's text individually. Slight uniform over-count from message overhead; preserves zero-vs-nonzero ordering.
- **The implication for the report.** Anyone replicating this experiment with the Anthropic SDK directly (rather than LiteLLM with its normalized `reasoning_tokens` field) needs to reproduce this workaround or rely on a fragile alternative. The brief's §5.4 example is LiteLLM-shaped; the harness's approach is the SDK-direct equivalent.

### 7.2 The hallucinated-PDF-prefix bug

Discovered in smoke #2 (`wiki-run-smoke-20260506T204641Z.json`). The model, when filling out `submit_answer`'s `sources` array with the canonical PDF filenames, occasionally invented domain-prefix variants — e.g. `ethics-anchor-considerations-qiu.pdf` for the precision-medicine paper `medicine-anchor-considerations-qiu.pdf`. Smoke #2 surfaced six unique hallucinations across two questions. Verify with:

```bash
jq '.results[].sources[] | .filename | select(endswith(".pdf"))' \
  experiments/results/wiki-run-smoke-20260506T204641Z.json | sort -u
# Includes "ethics-anchor-considerations-qiu.pdf" and "ethics-chrono-devote3-pieber.pdf"
# (both wrong-domain prefixes; the correct names start with "medicine-").
```

**Root cause.** The wiki's source-page frontmatter only stored slugs (e.g. `considerations-rct-rwd-integration`), not the canonical PDF filename. The model had to *generate* the PDF filename when filling out the source entry, and it inferred the domain prefix from context — which in a multi-domain prompt sometimes went wrong.

**Two-part fix:**

1. **Prompt side** (`harness.py:88-118`): embedded the §3 PDF-filename table directly in the system prompt, with author/year/title parentheticals and an explicit warning ("DO NOT invent variants like `ethics-chrono-devote3-pieber.pdf` for a precision-medicine paper"). This eliminated the bug at the source.
2. **Post-filter** (`harness.py:362-388`): the `CANONICAL_PDFS` set is the safety net. Any `*.pdf` filename not in the canonical 24 is dropped before output.

**Outcome.** Smoke #3 produced zero hallucinations, and the formal run produced zero hallucinations. The post-filter was never invoked — the prompt-side fix was sufficient on its own. The post-filter remains as belt-and-braces; if a future run does see hallucinations, the harness logs `[note] dropped N hallucinated PDF source entries` at submit time.

### 7.3 Ingest token apportionment is approximate

`experiments/README.md:44-56` and `wiki/analyses/build-cost-2026-05-06.md` are the canonical references. Summary of the issue:

The wiki was built across four roughly-arc-aligned sessions. The session-to-domain mapping isn't perfectly clean:

| Session | Mapped to domain | Caveat |
|---|---|---|
| `1e7548d8` (10 h 38 m) | ai-ethics-law | Includes wiki bootstrap (~1–2% of session, not strictly ethics) |
| `90769842` (7 h 16 m) | climate-science | Clean — single-arc |
| `0088cb9e` + `2f7ec7b7` | precision-medicine | `2f7ec7b7` also includes the post-medicine overview rewrite (a cross-arc operation, attributed to medicine for simplicity) |

Brief makes `by_domain` optional. Treat the per-domain numbers as ~5% noise. **H3 does not depend on per-domain precision** — it's an efficiency-class comparison, not a per-domain comparison.

Per-paper stopwatch totals (25 379 s = 7.05 h) are less than the JSONL-derived ≤2-min active total (8 h 19 m). The gap is lint passes plus the un-stopwatched ethics lint pass — folded into session-aggregated `totals.tokens_in/out` but not into per-paper `ingestion_seconds`. This is documented in `experiments/README.md:56`.

---

## 8. The smoke-test stabilization arc

Three smoke iterations on the same two-question subset (B1-devote3-confidence-interval + T3-rwd-validity-for-side-effects), each fixing a different harness defect. Useful for the report's "what we learned along the way" subsection because it shows the agentic-tool-loop pattern has multiple non-obvious failure modes.

### Iteration 1 — `wiki-run-smoke-20260506T204135Z.json` — broken thinking-token capture

Symptom:

```bash
jq '.results[].metadata.thinking_tokens' experiments/results/wiki-run-smoke-20260506T204135Z.json
# 0
# 0
```

Both questions returned `thinking_tokens = 0`. The first attempt at `_count_thinking_tokens` used the diff-against-stripped approach:

```python
# Broken: count_tokens rejects unmatched tool_use blocks → 400 every call → fall through to 0
full = count_tokens(messages=[{"role": "assistant", "content": resp.content}])
stripped = count_tokens(messages=[{"role": "assistant",
                                   "content": [b for b in resp.content if b.type != "thinking"]}])
return full.input_tokens - stripped.input_tokens
```

Fix: rewrite to per-thinking-block synthetic-user-message counting (§4.4). After the fix, smoke #2 showed thinking_tokens of 532 / 188 — both nonzero, consistent with adaptive thinking actually firing.

### Iteration 2 — `wiki-run-smoke-20260506T204641Z.json` — hallucinated cross-domain PDF prefixes

Symptom: six hallucinated PDF filenames in the citation lists across two questions (§7.2).

Fix: §3 PDF-filename table in the system prompt + `CANONICAL_PDFS` post-filter.

### Iteration 3 — `wiki-run-smoke-20260506T205038Z.json` — clean

Both fixes in place. Thinking tokens: 1 567 (T3) + 150 (B1). Citations: only canonical PDF filenames; no `[note] dropped` lines. Greenlit the formal run (`wiki-run-20260506T205500Z.json`, started ~5 min later at `205500Z`).

### What the report should take from this

The smoke iterations are evidence that the harness was not write-once-run-once. The two real bugs were both **invisible until you looked at the data**: the thinking-zeroes wouldn't have produced a malformed JSON, and the hallucinated PDFs are valid strings the schema accepts. The brief's §8 `jq` validation checks would have passed on smoke #1 and #2 cleanly. **Schema validation is not data validation.** The report should cite this as a methodology note — a future replication needs sanity checks on the *content*, not just the *shape*, of the artifacts.

---

## 9. What's NOT in this contribution — explicit gaps

The downstream session writing the full report should expect to fill these:

1. **PENDING — cross-family judged scores.** The `judged-<ts>.json` produced by `rag2compare`'s `rag2compare-judge` against this `wiki-run-...json` and the matching RAG-side run is not yet available. H1/H2 verdicts depend on these.
2. **PENDING — RAG-side per-query token totals.** Comparing the wiki's 1.55M prompt tokens / 87.8k completion / 9.4k thinking against the RAG side's equivalents is the H3 query-side comparison; numbers not yet in hand.
3. **PENDING — confirmation that the artifacts have been delivered.** As of session end on 2026-05-06, no signal on whether `wiki-run-20260506T205500Z.json` and `wiki-ingest-20260506T211731Z.json` have been picked up by the operator and paired against RAG-side artifacts. The report should confirm the handoff timestamp.
4. **NOT MEASURED — wiki ingest token attribution per paper.** Brief §5.5 makes per-paper tokens optional and we did not retro-fit the boundary annotation that would be required. H3 works at the corpus aggregate level; a per-paper breakdown would be a separate effort.
5. **NOT MEASURED — answer quality on the wiki side in isolation.** This document does not score answer correctness or groundedness; that is the cross-family judge's job.

---

## 10. Key file pointers (one-screen reference)

For the downstream session, in rough order of usefulness:

| File | What it gives you |
|---|---|
| `experiments/results/wiki-run-20260506T205500Z.json` | The 13 answers + per-question metadata. The artifact. |
| `experiments/results/wiki-ingest-20260506T211731Z.json` | Ingest cost totals + per-paper stopwatch + per-domain breakdown. |
| `WIKI_SIDE_BRIEF.md` | The contract: questions, schema, validation, model config. Sections most-cited above: §3 (corpus), §4 (questions), §5 (model), §7 (output schema), §8 (validation jq). |
| `experiments/harness.py` | Tool-loop, system prompt, post-filter, token-accounting. Line refs in §4. |
| `experiments/README.md` | Operator runbook + apportionment caveats. |
| `wiki/analyses/build-cost-2026-05-06.md` | Source of all ingest cost numbers. |
| `experiments/results/run_wiki_full.log` | 209-line per-turn trace of the formal run. Useful for sanity-checking turn counts and the `[submit_answer] sources=N` lines. |
| `experiments/results/wiki-run-smoke-*.json` (×3) | Evidence of the §8 stabilization arc. |
| `experiments/results/wiki-ingest-20260506T204023Z.json` | Pre-formal ingest snapshot. Same totals, earlier timestamp; useful only to confirm the ingest artifact is reproducible from the build-cost table. |

The smoke runs and the per-turn log are `.gitignore`d but on disk locally; if the report runs in a fresh checkout they won't be present. The two formal artifacts are committed and on `main`.

*End of contribution.*
