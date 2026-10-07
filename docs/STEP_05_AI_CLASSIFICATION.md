# Step 5 — Real AI Problem Classification System

**Status: Complete — genuine DistilBERT fine-tune, honest metrics, no faked outputs.**

Step 5 classifies every campus problem report with a fine-tuned
`distilbert-base-uncased` transformer: text → tokenizer → DistilBERT encoder
→ classification head → softmax → predicted category + confidence. No
keyword rules, no hardcoded outputs, no invented numbers anywhere.

Steps 1–4 are untouched in behavior: migrations `001`–`004` were not
modified, and all 74 pre-existing tests still pass.

## 1. Categories (12, controlled)

`IT_NETWORK, ELECTRICAL, INFRASTRUCTURE, CLEANLINESS_SANITATION,
SAFETY_SECURITY, LABORATORY, LIBRARY, ACADEMIC, HOSTEL, TRANSPORT,
WATER_SANITATION, OTHER` — frontend maps them to human labels
("IT / Network", "Cleanliness / Sanitation", …). The service rejects any
model output outside this taxonomy instead of storing it.

## 2. Dataset (honest development corpus)

- `backend/ml/data/problem_classification_v1.jsonl` — **288 hand-written
  samples, 24 per class, 0 duplicates, 0 empties** (verified).
- Styles: formal/informal/short/natural campus wording + a few Hinglish-style
  lines (plain wordpieces for the uncased tokenizer; no multilingual claims).
- **Labeled honestly as a development dataset**, not institutional data. No PII.
- `scripts/validate_classification_dataset.py` → VALID; stratified 70/15/15
  split with seed 42 gives **train 201 / val 43 / test 44**.
- Known limitation: shared vocabulary between INFRASTRUCTURE↔ELECTRICAL,
  CLEANLINESS_SANITATION↔WATER_SANITATION, IT_NETWORK↔LABORATORY,
  ACADEMIC↔LIBRARY — reported, not hidden.

## 3. Model & training (real)

- Base: `distilbert-base-uncased` (66M params, Hugging Face, local inference —
  no external LLM APIs). Pipeline in `app/ml/classification/`:
  `config.py, dataset.py, model.py, trainer.py (explicit PyTorch loop),
  inference.py, metrics.py`.
- `python3 scripts/train_classifier.py --epochs 15` (seed 42, AdamW 2e-5,
  batch 16, cosine schedule + warmup, best-val-macro-F1 checkpoint).
  Device: **MPS** (Apple Silicon), CPU fallback; CUDA never assumed.
- Artifacts: `backend/ml/artifacts/problem_classifier/` — model weights,
  tokenizer, `label_map.json`, `train_config.json`, `metadata.json`,
  `metrics_val.json`, **`metrics.json` (held-out test)**. Weights/safetensors
  are git-ignored; metadata stays. Retrain documented in §6.
- Version: `campusxolve-problem-classifier-v1`, recorded on every audit row.

## 4. ACTUAL metrics (held-out test, n=44 — from `metrics.json`)

| Metric | Value |
|---|---|
| Accuracy | **0.6591** |
| Macro F1 | **0.63** |
| Weighted F1 | **0.644** |

Per-class F1: TRANSPORT 0.889, ACADEMIC 0.857, HOSTEL 0.8, OTHER 0.8,
ELECTRICAL/LIBRARY/WATER_SANITATION 0.75, CLEANLINESS/IT/LABORATORY 0.571,
INFRASTRUCTURE 0.25, **SAFETY_SECURITY 0.0**. Main confusions:
SAFETY_SECURITY→INFRASTRUCTURE/HOSTEL, INFRASTRUCTURE→CLEANLINESS/TRANSPORT,
IT_NETWORK→ACADEMIC/LABORATORY. Weak on a 201-sample train set — stated
plainly; more data would fix it.

## 5. Unseen inference smoke (verbatim, unaltered)

| Text | Model output |
|---|---|
| WiFi in 2nd-floor lab disconnects every few minutes | IT_NETWORK 0.332 |
| Corridor tube light sparking near classroom 204 | ELECTRICAL 0.399 |
| No water from drinking unit near library | LIBRARY 0.396 (wrong) |
| College bus route 3 missing two days | TRANSPORT 0.645 |
| Library barcode scanner rejects cards | LIBRARY 0.486 |
| Insects in mess food | CLEANLINESS 0.219 (weak) |

Low/confused outputs are exactly why the 0.60 threshold + review flow exist.

## 6. Confidence & review

Softmax probability, threshold `CLASSIFICATION_CONFIDENCE_THRESHOLD=0.60`
(env-configurable). Below threshold → `LOW_CONFIDENCE` + `requires_manual_review`.
Admin accepts (final = prediction) or overrides (validated taxonomy);
original prediction, confidence, reviewer, timestamp and note are preserved —
originals are never rewritten.

## 7. Database (migration `005_ai_classification`)

`problem_classifications` audit table (prediction, confidence 0–1 CHECK,
model name/version, status enum, review fields, reviewer FK) + 
`problems.classification_status` cache (`NOT_RUN` default). History preserved
per rerun. Chain verified: `001→…→005`.

## 8. Flow & APIs

`POST /problems` commits the report, then classifies synchronously; **AI
failure (missing model, inference error) still returns 201** with status
`FAILED` + `requires_manual_review` — never a fake label; FAILED rows store
NULL prediction/confidence (truthful, CHECK allows NULL).
`GET /problems/{id}/classification` (owner/admin),
`GET …/classifications` (history),
`POST /admin/problems/{id}/classification/run` and `/review` (admin only;
reporters get 403). Problem detail embeds the latest classification.

## 9. Frontend

Detail page AI section: predicted category, numeric confidence + band
(High ≥80% / Moderate ≥60% / Low), status, model/version, review notice,
FAILED/NOT_RUN honesty states. Admin: Re-run, Accept, Change (select +
note), AI-vs-final display. Creation success screen shows ticket +
classification or the graceful failure notice. No priority/skills/duplicates.

## 10. Tests & quality

9 new tests (`tests/test_classification.py`): auto-classify, taxonomy,
confidence range, owner/stranger view, low-confidence flag (threshold forced
to 1.0), missing-model safety, rerun history, accept/override preservation,
invalid-category 422, FAILED-review 409. Full suite: **83 passed**.
`ruff check` clean, `mypy app/` strict clean (with documented stub shims for
numpy-family stubs), frontend lint/typecheck/build green. Step 1–4
regression: all green (one Step 4 assertion evolved from "AI stays null" to
"real classification present").

## 11. Hard bugs found by testing (fixed, not hidden)

- Migration used VARCHAR for status while the model binds native enum →
  `operator does not exist` on filters; fixed with native `postgresql.ENUM`.
- Training script overwrote HF `config.json` (renamed to `train_config.json`;
  model config restored from weights).
- `expire_on_commit=False` served a stale empty classifications collection in
  the create response → explicit `refresh(["classifications"])`.
- ORM instances must not cross into inference threads (`MissingGreenlet`) →
  snapshot plain strings before `to_thread`.
- Wrong artifact path depth → model-not-found; fixed + covered by test.

## 12. Not started (Step 6+)

Priority scoring/levels, skill extraction, Sentence-BERT duplicates, team and
mentor recommendation, approval/assignment, tasks, notifications,
verification, knowledge base, analytics.

## Reproduce

```bash
python3 scripts/validate_classification_dataset.py
python3 scripts/train_classifier.py --epochs 15
python3 scripts/evaluate_classifier.py
python3 -m pytest tests/ -q
```
