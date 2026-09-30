
# Human Validation of the Claim-Level Judge: Pre-Specification

> Shipped with the supplementary material. This is the pre-specification as it stood on
> 2026-09-19, before any annotator label existed (the first returned form is dated
> 2026-09-26). It is reproduced unedited except that internal cross-reference links
> are rendered as plain text, script paths point to this folder, and one internal
> machine name is replaced. Results, and a
> correction to the source-data note below, are in Appendix H of the revised paper.


All three reviewers of #11225 named the absence of human validation, and the round's one No rests partly on it. This page fixes the design before any human label exists: which claims were drawn, by what rule, who scores them, what will be reported, and what result would count against the paper.

## Why this page exists before the labels

Reviewer rTNr answered No on TMLR's first criterion and gave three reasons, of which the second is the only one narrowing cannot close: all quality evaluations are LLM-scored, and the paper itself demonstrates substantial inter-judge disagreement. Rewording leaves the fact that prompted the concern exactly where it was.

A human check chosen *after* its results are known would answer that objection with a new one, and it would do so in a paper whose argument rests on preregistration. So the sample, the contrasts and the reporting commitments are recorded here first. The seed is fixed, the draw is reproducible, and nothing below depends on a human label, because none exists yet.

> [!note] Scope
> This validates **the judge**, not the systems. It does not touch the paper's own interpretive caveat that the claim-level analysis measures evidence-artifact alignment rather than original-source fidelity. No reviewer asked about that caveat, and it stands unchanged.

## The universe

The claim-level artifact holds **466 scored claims**, of which **373 cite at least one source**: 132 from RAG and 241 from the wiki. Uncited claims receive `unsupported` automatically and are excluded, since there is nothing for a human to read against them. The per-tier counts reproduce Appendix D of the manuscript exactly, which is the check that the right artifact was loaded.

Two wrinkles in the source data, both reproduced rather than repaired, so that an annotator sees what the judge saw:

- **Two RAG claims cite a source index past the end of the source list**, both on `B2-he-tyka-equilibration-ratios`, where the atomizer emitted index 5 against five sources. The original scorer dropped the invalid index silently, and `n_cited_chunks` counts valid indices only. That invariant was verified across all 373 claims.
- **86 of the 241 wiki claims, 36%, cite byte-identical passages twice**, because a wiki answer can cite two source slots holding the same page excerpt. No RAG claim does. The judge saw the text concatenated. Each distinct passage is shown once, which changes no evidence and removes a signal that would otherwise identify the system.

## The draw

100 items, 50 per system, allocated across the six question tiers by largest remainder, drawn with `human_validation/sample_claims.py` at **seed 20260919**.

| Tier | RAG drawn / cited | Wiki drawn / cited |
|---|---|---|
| bias-check | 7 / 19 | 6 / 27 |
| chronological | 10 / 25 | 13 / 61 |
| conflict | 8 / 22 | 7 / 35 |
| emergence | 8 / 20 | 7 / 32 |
| multi-hop | 9 / 25 | 9 / 45 |
| policy | 8 / 21 | 8 / 41 |
| **Total** | **50 / 132** | **50 / 241** |

Stratification matters here because the tier rates are uneven. RAG's unsupported rate runs 78.9% on bias-check and 9.1% on conflict, so an unstratified draw would be noisy in a way that has nothing to do with the judge.

The draw is balanced by system rather than proportional to the 132/241 split, because the analysis compares the two systems and equal arms maximize power for a fixed total.

**Judge verdicts in the drawn sample**, recorded now so the composition is on file before any human sees it: supported 32, partial 40, unsupported 27, contradicted 1. Four contradicted claims exist in the 373, so drawing one is close to expectation.

Per system, the draw runs `unsupported` at 46.0% for RAG against 8.0% for the wiki, and `supported` at 12.0% against 52.0%. **Both gaps are wider than the population's**, which are 34.1% against 6.2%, and 18.9% against 40.2%. Part of that is by design, since the sample is balanced 50 and 50 where the population is 132 and 241. The rest is ordinary sampling variation: across all eight verdict-by-system margins the largest deviation from the stratified expectation is 2.54 standard deviations and the others fall between -2.07 and 1.86, which is unremarkable across eight correlated statistics. The consequence is a reporting one. **The response states the sample rates as sample rates and gives the population rates beside them**, and what protects that against a cherry-picking reading is that the seed was fixed and this composition was recorded before any label existed.

A separate **20-item calibration set** is drawn from the claims the sample did not take. Overlap with the scored 100 is zero, verified on the generated pack, so the calibration discussion cannot contaminate the result.

## Who scores, and what they are told

Two annotators, scoring independently. Neither is the author, because author-only scoring would not be independent of the result.

They are given the claim, the passages it cited, and the four verdict definitions transcribed from Appendix D, including its instruction to be strict on the supported-partial boundary. They are told to judge only whether the passages support the claim, not whether the claim is true in the world.

They are **not** told the research question, that two systems are being compared, which system produced any item, or what the paper claims. The item sheet carries no system name, no file name and no judge verdict.

## What will be reported

All of the following will be reported whatever the numbers say.

**P1. Judge-human agreement.** Raw agreement and Cohen's kappa on the four-way verdict, and again on the binary supported-versus-not-supported cut, against each annotator and against their adjudicated consensus. At n=100 the agreement estimate carries a 95% interval of about ±7.7 points at an agreement of 0.70, including the finite-population correction.

> [!note] Kappa will look modest, and that is expected
> `partial` takes roughly half the mass, and skewed marginals depress kappa even when agreement is good. This is why raw agreement and a binary cut are reported beside it rather than kappa alone.

**P2. Human-human agreement.** Reported first, because it sets the scale for everything after it. A modest P1 against a modest P2 indicates an ambiguous task rather than a failing judge. P1 landing *above* P2 is possible and is not by itself evidence that the judge beats a human: a rater sitting near the center of human disagreement agrees with each individual more than the individuals agree with each other. Reading P1 without P2 would be a mistake in either direction, and stating that here prevents it.

**P3. The unsupported-rate contrast on human labels.** The paper's strongest claim-level result is that wiki claims are 4 to 5 times less often unsupported than RAG claims, 6.2% against 34.1%. At 50 per arm this design detects a gap that size with better than 99% power.

**P4. The supported-rate contrast on human labels.** The wiki's claims are supported about twice as often, 40.2% against 18.9%. At 50 per arm this design has roughly 80% power, computed with the finite-population correction. It is the weaker of the two contrasts by design, and that is stated in advance rather than discovered afterward.

## What would count against the paper

A check that can only confirm is not a check. Each of these outcomes is reachable, and each carries a consequence recorded before the fact.

- **Binary judge-human agreement below 0.70, or kappa below 0.40**, the conventional floor for more than fair agreement, means the judge is not validated. The claim-level section would then be reported as LLM-scored without human corroboration, and its rates narrowed accordingly rather than defended.
- **A reversal or loss of significance on P3** means the paper's strongest claim-level result does not survive human scoring, and Section 5.4 would have to say so.
- **A failure to reach significance on P4** means the "about twice as often supported" sentence must be narrowed to the judged labels, since 80% power leaves a real chance of this outcome even if the effect is genuine. Failure to reach significance here is weak evidence of absence, and will be reported as such rather than as a refutation.

## Blinding: what this design does not have

The study is not fully blind, and the response will say so rather than claim otherwise.

RAG cites chunks targeting 512 tokens; the wiki cites short page excerpts. **A single length threshold classifies 97% of the items by system**, with only 25 of the 100 falling in the overlapping band of 104 to 300 words. An annotator who suspected two conditions existed could group the items almost perfectly.

Shortening the RAG passages to match would change the evidence and could flip verdicts, so it is not an option. What protects the result instead is that grouping items is not the same as knowing which group is which, or having any stake in which one scores better. The annotators are not told the research question, and a reviewer who downloads the supplement can compute the same 97% in a minute, so stating it is both honest and safer than leaving it to be found.

## A covariate recorded in advance

**RAG cites 5.9 times more evidence per claim than the wiki**, a median of 400 words against 68 across all 373 cited claims. The manuscript concedes a style and length confound, but only about *answer* length, where the wiki runs 1.9 times longer at 740 words against 385. Cited-evidence length runs the opposite way and appears nowhere in the paper.

It admits two readings. The wiki may cite less and still score better because its citations are more precisely targeted, which would strengthen the claim-level result. Or a short excerpt may simply be easier to match against a claim than a long chunk in which the relevant sentence has to be located first, which would make part of the advantage an artifact of excerpt granularity.

No reviewer has raised it. Rather than argue either reading, **cited-passage word count is recorded as a covariate and verdict-by-length will be reported within system**, which turns a possible new objection into a measured number. The data is already in the answer key, so this costs nothing.

## What is post-hoc

This study is post-hoc and will be labeled so, like the decomposition ablation and the claim-level analysis themselves. It was not part of the registered design, it was prompted by review, and the paper's preregistered-versus-exploratory partition is the one thing that must not blur. Nothing here migrates into the abstract.

## Provenance

The sample was generated by `human_validation/sample_claims.py` from three artifacts of record on the analysis machine: `grounding-20260508T155234Z.json`, `run-20260506T221602Z.json` and `wiki-run-20260506T205500Z.json`. The script aborts if the scored, cited and per-system counts do not match Appendix D. Atomizer `claude-opus-4-7`, scorer `gpt-5.4`, both recorded in the answer key beside the seed. The generated pack was verified byte-identical across two devices by sha256.

## Connections

- The paper under validation: cochran-vector-rag-vs-llm-wiki
- The No this answers, and its requested change 2: tmlr-review-rtnr-11225
- The other two reviewers who named human validation: tmlr-review-dbgr-11225, tmlr-review-agfd-11225
- The clock this runs against: tmlr-discussion-notice-11225
- The plan whose step 17 carries the decision: tmlr-submission-plan-vector-rag
- The tier-level evidence the sample is stratified on: claim-alignment-by-tier-vector-rag
- The dual-judge work that made judge disagreement measurable: decomp-dual-judge-vector-rag
- The method under test: llm-as-judge; the reliability frame: inter-rater-reliability
- What the exercise is ultimately about: construct-validity
- Author: theodore-cochran; organization: ai-for-altruism
