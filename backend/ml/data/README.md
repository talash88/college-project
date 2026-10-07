# Campus Problem Classification Dataset v1 (development dataset)

**Honest labeling: this is a small, hand-written development/project training
dataset created for this college project. It is NOT a large real-world
institutional complaint dataset.**

- File: `problem_classification_v1.jsonl` (JSONL, fields `text`, `label`)
- Size: 288 samples, 12 categories × 24 samples each
- Styles: formal English, informal English, short complaint style, natural
  campus wording, a few Hinglish-style lines ( romanized Hindi in Latin
  script — the DistilBERT uncased tokenizer handles these as ordinary
  wordpiece tokens; no special multilingual handling is claimed).
- No personally identifiable data. No duplicates, no empty samples
  (verified by `scripts/validate_classification_dataset.py`).
- Split: stratified 70/15/15 train/validation/test with fixed seed 42
  (see `app/ml/classification/dataset.py`).
- Known limitation: some category pairs share vocabulary (e.g.
  INFRASTRUCTURE vs ELECTRICAL, CLEANLINESS_SANITATION vs WATER_SANITATION,
  IT_NETWORK vs LABORATORY, ACADEMIC vs LIBRARY) and will confuse a small
  model. This is reported honestly in STEP 05 docs, not hidden.
