# Wiki-Side Brief — RAG vs LLM Wiki Experiment

| Field | Value |
|---|---|
| **Audience** | The team / Claude session executing the LLM Wiki side of the experiment |
| **Status** | Working document — pair with the rag2compare main branch |
| **Pairs with** | `experiments/rubric.yaml`, `backend/scripts/judge_runs.py` (the cross-family judge that scores both sides) |

This is everything you need to produce results that pair cleanly with the
RAG side under the cross-family judge. **You do not need to read the
RAG-side `RUNBOOK.md`** — it is mostly Docker / Qdrant / pipeline
operational detail that does not apply to a Wiki workflow.

The contract is narrow but strict. The judge pairs results by question
`id` and silently zero-fills missing fields, so a typo in an id or an
omitted metadata key will not error — it will just produce a wrong
judged artifact. Read §"Validation checklist" before delivery.

---

## 1. The experiment in two paragraphs

We are comparing two knowledge architectures over a fixed 24-paper
corpus across three domains (AI Ethics & Law, Climate Science,
Precision Medicine) using a single fixed answer model
(**Claude Opus 4.7 with `xhigh` adaptive thinking**). The RAG side
runs `rag2compare` (this repo). The Wiki side is built externally per
Karpathy's agentic-markdown architecture — it pre-compiles the corpus
into a persistent, cross-referenced knowledge wiki at ingest time,
then answers questions by traversing the wiki rather than retrieving
chunks at query time.

The hypotheses, in shorthand:

- **H1 (synthesis):** Wiki should beat RAG on multi-hop questions
  requiring 3+ papers (Tier 3, Tier 4).
- **H2 (fact retrieval):** RAG should match-or-beat Wiki on
  point-source factual lookups (the three `bias-check` questions).
- **H3 (efficiency):** Wiki pays a high cost at ingest time; RAG pays
  per-query. Crossover depends on corpus size and query volume.

You produce two artifacts. The judge pairs them with the RAG side's
artifacts and writes a `judged-*.json` that drives the analysis.

---

## 2. Hard contracts (read this twice)

Three things must match exactly between your output and the RAG side.
Everything else is flexible.

### 2.1 Question ids

The judge pairs by `id`. The 13 ids you must answer are listed
verbatim in §4. **Do not paraphrase, renumber, lowercase, or add
prefixes.** A mismatched id is silently dropped from the judged set.

### 2.2 Paper filenames in `sources[].filename`

Use the exact filenames in §3. If the Wiki cites a wiki page derived
from a paper, prefer the wiki-page filename (e.g.
`wiki/ai-ethics-law/tdm-exception.md`) but always include the source
paper filename in the chunk_text or in a sibling source entry. The
judge surfaces filenames to the human reviewer; consistent naming
matters for un-blinding.

### 2.3 Answer model identity

Both sides answer with **`claude-opus-4-7`** at **xhigh** adaptive
thinking. Don't substitute a different model "for cost reasons" —
H1/H2 only mean something if the answer model is held constant. If
you must downgrade, document it explicitly in `metadata.model_used`
and flag it for the analysis writeup; the judged artifact records
this verbatim.

---

## 3. The corpus (24 papers, 3 collections)

The RAG side ingests these PDFs in role order
(`Anchor → Chrono → Bridge → Conflict`). Your Wiki should include
content from all 24, organized however your wiki structure prefers.
The role tags are advisory for ingest sequencing, not authoritative
metadata.

### ai-ethics-law (8 papers)

| Filename | Role | Year | Authors | Title |
|---|---|---|---|---|
| `ethics-anchor-generative-ai-stober.pdf` | Anchor | 2026 | Stober & Dornis | Generative AI Training and Copyright Law |
| `ethics-anchor-creative-ownership-liang.pdf` | Anchor | 2026 | Liang & Lut | Creative Ownership in the Age of AI |
| `ethics-bridge-g-drift-ranjan.pdf` | Technical Bridge | 2026 | Ranjan et al. | G-Drift MIA — Membership Inference via Gradient-Induced Feature Drift in LLMs |
| `ethics-bridge-membership-inference-liu.pdf` | Technical Bridge | 2026 | Liu et al. | Membership Inference Attack Against Music Diffusion Models |
| `ethics-conflict-yes-but-hutiri.pdf` | Conflict | 2026 | Hutiri & Scheuerman | Yes, But Not Always — Generative AI Needs Nuanced Opt-in |
| `ethics-conflict-unfair-learning-atkinson.pdf` | Conflict | 2025 | Atkinson | Unfair Learning — GenAI Exceptionalism and Copyright Law |
| `ethics-chrono-assessing-effectiveness-chow.pdf` | Chrono | 2025 | Chow et al. | Assessing the Effectiveness of Membership Inference on Generative Music |
| `ethics-chrono-label-only-choquette.pdf` | Chrono | 2021 | Choquette-Choo et al. | Label-Only Membership Inference Attacks |

### climate-science (8 papers)

| Filename | Role | Year | Authors | Title |
|---|---|---|---|---|
| `climate-anchor-climate-targets-oschlies.pdf` | Anchor | 2023 | Oschlies et al. | Climate Targets, Carbon Dioxide Removal, and the Potential Role of OAE |
| `climate-chrono-limits-co2-he.pdf` | Chrono/Anchor | 2023 | He & Tyka | Limits and CO2 Equilibration of Near-Coast Alkalinity Enhancement |
| `climate-bridge-monitoring-reporting-ho.pdf` | Meta Bridge | 2023 | Ho et al. | Monitoring, Reporting, and Verification for Ocean Alkalinity Enhancement |
| `climate-bridge-lit-tag-mcelhany.pdf` | Meta Bridge | 2026 | McElhany et al. | lit-tag — A Shiny App for Adding Custom Tags and Notes to a Citation Database |
| `climate-chrono-novel-field-savoie.pdf` | Chrono | 2025 | Savoie et al. | Novel Field Trial for OAE Using Electrochemically Derived Aqueous Alkalinity |
| `climate-conflict-biological-response-jones.pdf` | Conflict | 2025 | Jones et al. | Biological Response of Eelgrass Epifauna to Elevated Ocean Alkalinity |
| `climate-conflict-air-sea-schneider.pdf` | Conflict | 2025 | Schneider et al. | Air-Sea Gas Exchange in Response to OAE in a Temperate Plankton Community |
| `climate-conflict-modeling-oae-nagwekar.pdf` | Conflict | 2025 | Nagwekar | Modeling Ocean Alkalinity Enhancement in Subduction Regions and the Global Ocean |

### precision-medicine (8 papers)

| Filename | Role | Year | Authors | Title |
|---|---|---|---|---|
| `medicine-anchor-considerations-qiu.pdf` | Anchor | 2026 | Qiu et al. | Considerations for the Integration of RCTs and Real-World Data |
| `medicine-anchor-glp-1-kupnicka.pdf` | Anchor | 2024 | Kupnicka et al. | GLP-1 Receptor Agonists — A Promising Therapy for Modern Lifestyle Diseases |
| `medicine-bridge-ai-enabled-barakat.pdf` | Technical Bridge | 2026 | Barakat et al. | AI-Enabled Personalization of Semaglutide Therapy in Type 2 Diabetes |
| `medicine-bridge-progress-berberine-kong.pdf` | Bridge | 2025 | Kong et al. | Progress of the Anti-Obesity of Berberine |
| `medicine-conflict-joint-qol-martinussen.pdf` | Conflict | 2026 | Martinussen et al. | A Joint QoL-Survival Framework with Debiased Estimation under Truncation by Death |
| `medicine-conflict-self-reported-sehgal.pdf` | Conflict | 2026 | Sehgal et al. | Self-Reported Side Effects of Semaglutide and Tirzepatide in Online Communities |
| `medicine-chrono-risk-protective-beheshti.pdf` | Chrono | 2025 | Beheshti | Risk and Protective Factors in Parkinson's Disease |
| `medicine-chrono-devote3-pieber.pdf` | Chrono/Baseline | 2017 | Pieber et al. | DEVOTE 3 — Severe Hypoglycaemia, Cardiovascular Outcomes and Mortality |

---

## 4. The 13 evaluation questions (verbatim)

Each question has `id`, `tier`, `bias`, `collections`, `text`. **Do
not modify any field.** The judge reads `id` for pairing, `tier` and
`bias` for aggregation. Ten questions are written to favor Wiki
synthesis (Tiers 1-5), three are bias-check questions where RAG
should excel.

### Tier 1 — Chronological evolution (2 questions, neutral)

```yaml
- id: T1-cardio-baselines
  tier: chronological
  bias: neutral
  collections: [precision-medicine]
  text: |
    Based on the DEVOTE 3 trial and the 2026 Qiu et al. framework for
    integrating RCTs with real-world data, what are the current standard
    cardiovascular risk baselines used to evaluate new GLP-1 analogs, and
    how does the 2026 framework revise the interpretation of the 2017
    DEVOTE 3 numbers?

- id: T1-mia-evolution
  tier: chronological
  bias: neutral
  collections: [ai-ethics-law]
  text: |
    How have membership inference attacks against generative-audio models
    evolved from the 2021 label-only formulation (Choquette-Choo et al.)
    through the 2025 effectiveness assessments to the 2026 LSA-Probe /
    manifold-perturbation methodology described by Liu et al.? Treat this
    as a technical evolution, not a list.
```

### Tier 2 — Conflict detection (2 questions, wiki-favoring)

```yaml
- id: T2-oae-bio-vs-chemical
  tier: conflict
  bias: wiki
  collections: [climate-science]
  text: |
    Contrast the He & Tyka (2023) chemical-efficiency model for near-coast
    OAE with the 2025 Schneider et al. findings on biological influence on
    air-sea gas exchange. Does biological activity accelerate or
    decelerate equilibration, and where do the papers actually disagree
    versus agree on mechanism?

- id: T2-fair-use-vs-optin
  tier: conflict
  bias: wiki
  collections: [ai-ethics-law]
  text: |
    How does the "Unfair Learning" argument (Atkinson, 2025) conflict
    with the "Nuanced Opt-in" proposal (Hutiri & Scheuerman, 2026) on
    the status of publicly available training data? Identify the
    specific claim each paper makes and where they are not actually
    addressing the same question.
```

### Tier 3 — Multi-hop technical synthesis (2 questions, wiki-favoring)

```yaml
- id: T3-mia-as-copyright-evidence
  tier: multi-hop
  bias: wiki
  collections: [ai-ethics-law]
  text: |
    Propose a forensic workflow that uses the G-Drift gradient-induced
    feature drift (Ranjan et al., 2026) to detect whether a specific
    training set was used by a target model, and connect it to the
    "counterfactual infringement" criterion proposed by Liang & Lut
    (2026) and the substantial-similarity threshold discussed in
    Stober & Dornis (2026). Be explicit about which paper supports
    each step.

- id: T3-rwd-validity-for-side-effects
  tier: multi-hop
  bias: wiki
  collections: [precision-medicine]
  text: |
    Using the Qiu et al. (2026) framework for integrating RCTs and
    real-world data, analyze whether the Reddit-sourced GLP-1 side
    effects reported by Sehgal et al. (2026) meet the criteria for
    regulatory-grade real-world evidence, and what additional analysis
    (per Martinussen et al.'s QoL-survival framework) would be needed
    to draw safety conclusions.
```

### Tier 4 — Emergence / discovery (2 questions, wiki-favoring)

```yaml
- id: T4-eelgrass-mrv-gaps
  tier: emergence
  bias: wiki
  collections: [climate-science]
  text: |
    Based on Jones et al.'s (2025) study of eelgrass epifauna response
    to elevated ocean alkalinity and Ho et al.'s (2023) MRV protocols
    for OAE, identify three potential ecological bottlenecks that
    current MRV protocols fail to monitor. For each, cite which paper
    supports the gap.

- id: T4-cross-domain-audit
  tier: emergence
  bias: wiki
  collections: [ai-ethics-law, precision-medicine]
  text: |
    How could a researcher use the G-Drift MIA technical mechanism
    and the counterfactual-infringement framework to audit whether
    DEVOTE 3 trial data was used to train a medical personalization
    model (e.g. the AI-enabled semaglutide personalization in Barakat
    et al. 2026) without authorization? Identify which step requires
    which paper.
```

### Tier 5 — Policy / strategy (2 questions, wiki-favoring)

```yaml
- id: T5-glp1-policy
  tier: policy
  bias: wiki
  collections: [precision-medicine]
  text: |
    Develop a policy recommendation for a national health board on
    the use of AI-enabled semaglutide personalization, incorporating
    Martinussen et al.'s warning about survival-truncation bias in
    QoL endpoints and the Qiu et al. (2026) RCT/RWD integration
    framework. Avoid a generic recommendation — anchor each clause to
    a specific paper.

- id: T5-25th-paper
  tier: policy
  bias: wiki
  collections: [ai-ethics-law, climate-science, precision-medicine]
  text: |
    If you were to add a 25th paper to this corpus, should it focus
    on (a) the pharmacokinetics of GLP-1 receptor agonists, (b) the
    chemical precipitation of NaOH in seawater for OAE, or (c) the
    EU legal status of "style" in generative AI? Justify the choice
    based on knowledge orphans / weakly-connected concepts visible in
    the current corpus.
```

### Bias-check — point-source retrieval (3 questions, RAG-favoring)

These are the H2 fairness check. Don't paraphrase or "improve" the
specificity — exact-quote questions test point-source retrieval.

```yaml
- id: B1-devote3-confidence-interval
  tier: bias-check
  bias: rag
  collections: [precision-medicine]
  text: |
    What is the exact reported hazard ratio and 95% confidence
    interval for the primary cardiovascular outcome in the DEVOTE 3
    trial results section?

- id: B2-he-tyka-equilibration-ratios
  tier: bias-check
  bias: rag
  collections: [climate-science]
  text: |
    In He & Tyka (2023), what is the specific range of mol DIC
    uptake per mol NaOH added that the paper reports for near-coast
    alkalinity enhancement? Cite the exact numbers and any conditions
    attached.

- id: B3-mia-attack-success-rate
  tier: bias-check
  bias: rag
  collections: [ai-ethics-law]
  text: |
    What attack success rate (or AUROC) does Choquette-Choo et al.
    (2021) report for label-only membership inference attacks on the
    CIFAR-10 dataset? Quote the value and the attack variant.
```

---

## 5. Answer-model configuration (Anthropic Claude Opus 4.7)

The RAG side learned the API contract for Opus 4.7 + adaptive
thinking the hard way. Skip that pain.

### 5.1 Required request shape

```python
import litellm  # or anthropic SDK; equivalent shape

response = await litellm.acompletion(
    model="claude-opus-4-7",
    messages=[
        {"role": "system", "content": <your wiki traversal/answer prompt>},
        {"role": "user", "content": <question text>},
    ],
    thinking={"type": "adaptive", "display": "summarized"},
    output_config={"effort": "xhigh"},
    max_tokens=16000,
    # NO temperature, top_p, or top_k — see §5.3.
)
```

### 5.2 What each field does

| Field | Why it must look like this |
|---|---|
| `thinking.type = "adaptive"` | Opus 4.7 rejects the legacy `{"type":"enabled","budget_tokens":N}` shape with HTTP 400 ("not supported for this model"). Adaptive thinking is the only supported shape. |
| `thinking.display = "summarized"` | Opus 4.7's default is `"omitted"`. With omitted, thinking content blocks are suppressed *and* `reasoning_tokens` returns 0 even when thinking ran. Setting `summarized` is required for the H3 token-cost analysis to capture thinking spend. |
| `output_config.effort = "xhigh"` | Soft guidance for how much thinking Claude allocates. `xhigh` matches Claude Code's xhigh preset; `max` is the absolute ceiling. The RAG side uses `xhigh`. |
| `max_tokens = 16000` | Hard cap on total output tokens (text + thinking). Adaptive thinking can run long; 16K matches Anthropic's documented xhigh example. |
| **no `temperature`** | Opus 4.7 returns HTTP 400 with `temperature is deprecated for this model.` Don't pass it. |

### 5.3 Adaptive thinking is opportunistic

Even at `xhigh` effort, Claude decides per-request whether to engage
explicit thinking. RAG-style synthesis prompts ("answer based on the
provided context") often score `thinking_tokens = 0`, while reasoning
prompts ("show your step-by-step working") score 50-1000+. **A zero
thinking_tokens count on a Wiki answer is not a bug** — record it
honestly and the judge will treat it as a real datapoint for H3.

### 5.4 Capturing token usage

LiteLLM normalizes Anthropic's response. After the call:

```python
usage = response.usage
prompt_tokens     = usage.prompt_tokens
completion_tokens = usage.completion_tokens
thinking_tokens   = getattr(
    getattr(usage, "completion_tokens_details", None),
    "reasoning_tokens",
    0,
) or 0
```

If you call the Anthropic SDK directly, the equivalent fields are
`usage.input_tokens`, `usage.output_tokens`, and the per-content-block
tokens for thinking blocks (sum them).

### 5.5 What "ingest" means on the Wiki side

Your ingest is whatever process compiles the 24 PDFs into the wiki
representation. Capture wall-clock time per paper and (if at all
possible) per-paper input/output tokens. The H3 hypothesis is the
*only* analysis that benefits from token-level ingest accounting; if
your tooling can't capture per-paper tokens, leave them as `null`
rather than synthesizing.

---

## 6. Output schema — `wiki-ingest-<ts>.json`

Drop this file at `experiments/results/wiki-ingest-<UTC-timestamp>.json`
in the rag2compare repo (or wherever you and the operator agree to
exchange artifacts).

### 6.1 Schema

```jsonc
{
  "started_at": "<ISO 8601 UTC, e.g. 20260520T143000Z>",   // required
  "documents": [                                              // required
    {
      "filename": "<exact filename from §3>",                 // required
      "domain": "ai-ethics-law" | "climate-science" | "precision-medicine",  // required
      "role": "<role tag from §3, optional but useful>",      // optional
      "ingestion_seconds": <float>,                           // required
      "status": "complete" | "completed" | "failed",          // required (either spelling accepted)
      "error_message": "<string or null>",                    // optional
      "tokens_in": <int>,                                     // optional but H3-useful
      "tokens_out": <int>                                     // optional but H3-useful
    },
    ...
  ],
  "totals": {                                                 // required
    "documents": 24,
    "completed": 24,
    "total_seconds": <float>,
    "tokens_in": <int>,                                       // optional
    "tokens_out": <int>,                                      // optional
    "by_domain": {                                            // optional but useful
      "ai-ethics-law":      { "documents": 8, "completed": 8, "total_seconds": <float>, "tokens_in": <int>, "tokens_out": <int> },
      "climate-science":    { "documents": 8, "completed": 8, "total_seconds": <float>, "tokens_in": <int>, "tokens_out": <int> },
      "precision-medicine": { "documents": 8, "completed": 8, "total_seconds": <float>, "tokens_in": <int>, "tokens_out": <int> }
    }
  }
}
```

### 6.2 Notes

- `status` accepts both spellings because the RAG pipeline emits
  `"complete"` and the runbook examples used `"completed"`. The judge
  ignores this artifact entirely; it's for H3 analysis only.
- If a paper fails to ingest, set `status: "failed"` and put the
  error in `error_message`. Don't silently drop it — the H3 analysis
  needs to know the corpus was complete.
- `tokens_in` / `tokens_out` are summed across whatever LLM calls your
  ingest pipeline made for that paper.

---

## 7. Output schema — `wiki-run-<ts>.json` (the one that matters)

This is the artifact the judge reads. **Schema correctness is
load-bearing**: missing fields are silently zero-filled.

Drop at `experiments/results/wiki-run-<UTC-timestamp>.json`.

### 7.1 Schema

```jsonc
{
  "started_at": "<ISO 8601 UTC>",                             // required
  "model_used": "claude-opus-4-7",                            // required
  "reasoning_effort": "xhigh",                                // required
  "results": [                                                // required, length 13
    {
      "id": "<one of the 13 ids verbatim from §4>",           // required, exact match
      "tier": "<from §4>",                                    // required
      "bias": "<from §4>",                                    // required
      "text": "<question text from §4, verbatim>",            // required
      "answer": "<the model's answer>",                       // required
      "sources": [                                            // required, can be empty array
        {
          "filename": "<wiki page or paper filename>",        // required
          "page_numbers": [<ints>] or [],                     // required, [] for wiki pages
          "chunk_text": "<verbatim excerpt or wiki snippet>", // required
          "relevance_score": <float>                          // optional
        },
        ...
      ],
      "metadata": {                                           // required
        "model_used": "claude-opus-4-7",                      // required
        "reasoning_effort": "xhigh",                          // required
        "latency_ms": <int>,                                  // required
        "prompt_tokens": <int>,                               // required
        "completion_tokens": <int>,                           // required
        "thinking_tokens": <int>                              // required (0 is a valid value)
      }
    },
    ...
  ]
}
```

### 7.2 Per-field requirements

| Field | What it must contain |
|---|---|
| `results[].id` | Exact byte-for-byte match against §4. The judge pairs by this. A typo silently drops the question from the judged set. |
| `results[].tier` / `bias` | Exact match against §4. The judge aggregates by tier; a misspelled tier creates a phantom group in the rollup. |
| `results[].text` | Verbatim from §4 (including newlines and indentation in the YAML literal blocks). The judge passes this to the scoring LLM as the question to evaluate against. |
| `results[].answer` | The Wiki's full answer. Plain text or markdown is fine; no length requirements. |
| `results[].sources` | Whatever the Wiki considers source material for that answer. Can include wiki page filenames (e.g. `wiki/ai-ethics-law/tdm-exception.md`), paper filenames from §3, or both. The judge surfaces these to score `groundedness` and `inter_paper_mapping`. **If the wiki cited zero specific sources, return `[]` rather than fabricating one** — empty sources is honest data for H1/H2. |
| `results[].sources[].chunk_text` | The verbatim excerpt the answer leaned on. For a Wiki this is typically the paragraph from the wiki page; the judge uses it to verify groundedness. |
| `metadata.thinking_tokens` | 0 is a valid value (see §5.3). Do not synthesize — record what the API returned. |

### 7.3 Worked example (one question)

```json
{
  "id": "T2-fair-use-vs-optin",
  "tier": "conflict",
  "bias": "wiki",
  "text": "How does the \"Unfair Learning\" argument (Atkinson, 2025) conflict\nwith the \"Nuanced Opt-in\" proposal (Hutiri & Scheuerman, 2026) on\nthe status of publicly available training data? Identify the\nspecific claim each paper makes and where they are not actually\naddressing the same question.\n",
  "answer": "Atkinson (2025) and Hutiri & Scheuerman (2026) appear to disagree but largely talk past each other. Atkinson's claim is structural: that GenAI exceptionalism in copyright doctrine — the assumption that training is categorically different from prior reproduction-rights cases — is unfair on its own terms regardless of consent mechanisms [Source 1]. Hutiri & Scheuerman accept the general legitimacy of training but argue that the publicly-available default is too coarse and propose a nuanced opt-in regime keyed to use-case, sensitivity, and proof of harm [Source 2]. The non-overlap is sharp: Atkinson is about doctrine (should the legal frame even apply this way?), while Hutiri & Scheuerman are about mechanism (assuming we permit training, how should consent flow?). They would converge only if Atkinson's doctrinal critique invalidated training entirely — and Atkinson does not actually go that far.",
  "sources": [
    {
      "filename": "wiki/ai-ethics-law/genai-exceptionalism.md",
      "page_numbers": [],
      "chunk_text": "Atkinson 2025 — argues GenAI exceptionalism in copyright doctrine is unfair on its own terms. Cross-refs: Stober & Dornis 2026 on TDM whitewashing.",
      "relevance_score": 0.91
    },
    {
      "filename": "wiki/ai-ethics-law/opt-in-regimes.md",
      "page_numbers": [],
      "chunk_text": "Hutiri & Scheuerman 2026 — accept training legitimacy, propose nuanced opt-in keyed to use-case / sensitivity / proven harm. Distinct from blanket consent regimes.",
      "relevance_score": 0.88
    }
  ],
  "metadata": {
    "model_used": "claude-opus-4-7",
    "reasoning_effort": "xhigh",
    "latency_ms": 18420,
    "prompt_tokens": 2810,
    "completion_tokens": 312,
    "thinking_tokens": 0
  }
}
```

---

## 8. Validation checklist (run before delivery)

If you have `jq` available, the following one-liners catch most
schema errors. Run them against your `wiki-run-<ts>.json` before
handing off.

```bash
WIKI_RUN=path/to/wiki-run-<ts>.json

# 1. All 13 question ids present, no duplicates, exact match.
EXPECTED='T1-cardio-baselines T1-mia-evolution T2-oae-bio-vs-chemical T2-fair-use-vs-optin T3-mia-as-copyright-evidence T3-rwd-validity-for-side-effects T4-eelgrass-mrv-gaps T4-cross-domain-audit T5-glp1-policy T5-25th-paper B1-devote3-confidence-interval B2-he-tyka-equilibration-ratios B3-mia-attack-success-rate'
ACTUAL=$(jq -r '.results[].id' "$WIKI_RUN" | sort | uniq -c | awk '{print $1, $2}')
echo "Expected 13 unique ids, one each. Actual:"
echo "$ACTUAL"

# 2. Every required field present on every result.
jq '.results[] | select(
  (.id      | type) != "string" or
  (.tier    | type) != "string" or
  (.bias    | type) != "string" or
  (.text    | type) != "string" or
  (.answer  | type) != "string" or
  (.sources | type) != "array"  or
  (.metadata.model_used        | type) != "string" or
  (.metadata.latency_ms        | type) != "number" or
  (.metadata.prompt_tokens     | type) != "number" or
  (.metadata.completion_tokens | type) != "number" or
  (.metadata.thinking_tokens   | type) != "number"
) | {id, missing: "see above"}' "$WIKI_RUN"
# If this prints anything, something is missing. Empty output = good.

# 3. model_used is claude-opus-4-7 across the board.
jq -r '.results[].metadata.model_used' "$WIKI_RUN" | sort -u
# Expected: a single line, "claude-opus-4-7"

# 4. Token counts are non-negative integers.
jq '.results[] | select(
  (.metadata.prompt_tokens     < 0) or
  (.metadata.completion_tokens < 0) or
  (.metadata.thinking_tokens   < 0)
) | .id' "$WIKI_RUN"
# Expected: empty.

# 5. Question text matches §4 (length sanity check; substring works for spot-check).
jq -r '.results[] | "\(.id): \(.text | length) chars"' "$WIKI_RUN"
```

Pair-test against a synthetic RAG run before the real run lands:

```bash
# Use the test-rag-run.json the operator can supply, then dry-run the judge.
docker compose exec backend rag2compare-judge \
  --rag-run /app/experiments/results/test-rag-run.json \
  --wiki-run /app/experiments/results/wiki-run-<ts>.json \
  --rubric /app/experiments/rubric.yaml \
  --judge-model gpt-5.4 \
  --dry-run
```

The dry-run prints the planned A/B blinding for each paired question.
If you see fewer than 13 lines or any "only in RAG" warnings, the
ids are mismatched.

---

## 9. What not to do

- **Don't paraphrase questions.** Copy the `text` field byte-for-byte
  from §4 — same newlines, same trailing whitespace, same
  capitalization. The judge passes this to the scoring LLM, and a
  Wiki answer that matches a slightly-different question against the
  rubric drifts in unobvious ways.
- **Don't skip questions.** If the Wiki refuses to answer, return
  `answer: "<wiki's refusal text>"` and `sources: []`. The judge
  scores empty answers as low groundedness, which is the correct
  signal.
- **Don't fabricate sources.** Empty `sources: []` is honest. A
  fabricated wiki-page filename inflates groundedness scores.
- **Don't average runs.** One pass at xhigh effort, recorded as-is.
  H3 needs single-run cost numbers.
- **Don't switch models mid-run.** Same model for all 13 questions.
  If a model upgrade lands between Wiki ingest and Wiki query,
  re-run the queries on the new model rather than mixing.
- **Don't run with thinking off.** `output_config.effort = "off"`
  changes the experimental condition. Use xhigh; if Claude declines
  to think on a particular query (see §5.3), record the 0 honestly.

---

## 10. Handoff back to the operator

Deliver these two files (named with your UTC timestamp):

```
experiments/results/wiki-ingest-<ts>.json
experiments/results/wiki-run-<ts>.json
```

The operator will then run:

```bash
docker compose exec backend rag2compare-judge \
  --rag-run  /app/experiments/results/run-<rag-ts>.json \
  --wiki-run /app/experiments/results/wiki-run-<wiki-ts>.json \
  --rubric   /app/experiments/rubric.yaml \
  --judge-model gpt-5.4
```

That produces `judged-<ts>.json` containing per-question scores plus
aggregates by tier. From there the H1/H2/H3 analysis runs against
both the judged scores and the ingest+run token totals.

If the judge flags missing or ambiguous data (e.g., a question id
doesn't pair, a tier is malformed), fix the wiki-run.json and re-run
— the judge has `--resume` so re-judging is cheap.

---

*End of brief.*
