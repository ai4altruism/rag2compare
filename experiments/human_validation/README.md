# Human validation of the claim-level scorer

Post-hoc, added in the 2026-09 revision. The design and decision rule were fixed
in `PRESPECIFICATION.md` before any label existed; results are in Appendix H of
the revised paper.

| File | What it is |
|---|---|
| `PRESPECIFICATION.md` | The design as fixed on 2026-09-19: sample, annotators, decision rule, analyses |
| `sample_claims.py` | Draws the 100-claim stratified sample at seed 20260919 from the grounding artifact |
| `analyze_claims.py` | The pre-specified analyses (P1 to P4 and the decision rules) |
| `posthoc_claims.py` | Post-hoc: agreement by cut exposure, and the rescored judge against the annotators |
| `labels/response_form_1.csv`, `labels/response_form_2.csv` | Each annotator's verdicts, by item; annotators are anonymous and their notes are not shipped |

Reproduce, from the supplement root (`--grounding` is relative to `experiments/results/`):

```
python3 experiments/human_validation/sample_claims.py \
    --grounding post-hoc/grounding-20260508T155234Z.json --out pack
cp experiments/human_validation/labels/response_form_*.csv pack/
python3 experiments/human_validation/analyze_claims.py --pack pack
python3 experiments/human_validation/posthoc_claims.py --pack pack \
    --rescore experiments/results/post-hoc/rescore-main-capnone-20260928T113149Z.json \
    --control experiments/results/post-hoc/rescore-main-cap1500-rag-20260928T113351Z.json
python3 experiments/claim_level_figures.py \
    --main experiments/results/post-hoc/rescore-main-capnone-20260928T113149Z.json \
    --decomp experiments/results/post-hoc/rescore-decomp-capnone-20260928T201439Z.json
```

The rescoring itself, `experiments/rescore_claim_grounding.py`, calls the scorer
model and needs an API key; its outputs are the three `rescore-*.json` artifacts.
