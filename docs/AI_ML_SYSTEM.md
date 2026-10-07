# AI / ML System (viva-critical — all values from real artifacts/code)

No external LLM APIs are used anywhere. Three learned components
(DistilBERT classifier, MiniLM sentence embeddings, skill-embedding table) plus
deterministic explainable engines (priority, recommenders), all gated by humans.

## 1. DistilBERT classification

- Base: `distilbert-base-uncased`; version `campusxolve-problem-classifier-v1`;
  trained 2026-09-26 (`scripts/train_classifier.py`), 21 s on MPS.
- Dataset: `ml/data/problem_classification_v1.jsonl`, **288 development-labelled
  campus complaints, 12 categories × 24**, split 201 train / 43 val / 44 test
  (stratified, seed 42). Labels: ACADEMIC, CLEANLINESS_SANITATION, ELECTRICAL,
  HOSTEL, INFRASTRUCTURE, IT_NETWORK, LABORATORY, LIBRARY, OTHER,
  SAFETY_SECURITY, TRANSPORT, WATER_SANITATION.
- Input: `title + description (+ location)` tokenized (tracked `tokenizer.json`);
  softmax confidence; review threshold **0.60** (`CLASSIFICATION_CONFIDENCE_THRESHOLD`).
  Below threshold → `LOW_CONFIDENCE` + `requires_manual_review`; missing
  artifact → `FAILED` (report still saves — proven by test + honest UI).
- **Held-out test metrics (44 samples, development data — NOT production
  accuracy)**: accuracy **0.659**, macro F1 **0.63**, weighted F1 **0.644**.
  Per-class F1: ACADEMIC 0.86, HOSTEL 0.80, OTHER 0.80, ELECTRICAL/LIBRARY 0.75,
  TRANSPORT ~0.89 (P 0.8/R 1.0), IT_NETWORK/LABORATORY/CLEANLINESS ~0.57,
  **INFRASTRUCTURE 0.25, SAFETY_SECURITY 0.0** (weak classes).
- Why human review exists: 44 test samples is tiny; weak classes overlap
  semantically (e.g. plaster damage → ACADEMIC). The system therefore never
  auto-acts on low confidence — admin accepts/corrects (`final_category`,
  original preserved). Live probes: 5/6 correct, all low-confidence.

## 2. Priority engine (deterministic, explainable — not black-box ML)

Deliberately rule-based so every point is attributable: severity **30** (risk
lexicon with negation handling, e.g. "not urgent" neutralized) + affected
people **25** (monotonic mapping of `affected_people_count`) + age **20**
(older unresolved accrues) + category context **15** (capped — never dominant)
+ confirmed duplicates **10** (cluster size contribution). Score 0–100;
bands LOW ≤29 / MEDIUM ≤54 / HIGH ≤79 / CRITICAL >79
(`PRIORITY_LOW_MAX` etc.). Each run appends a history row with per-component
contributions and human-readable reasons (UI "Why?" + breakdown). Terminal
reports freeze their score. Limitation: conservative — safety wording without
lexicon hits scores LOW (Step-16 probe: 18); admin judgment covers the gap.

## 3. Required skill extraction (hybrid)

Taxonomy of 46 skills; per report: (a) exact phrase/alias match, (b) cosine
between report embedding and skill embeddings (all-MiniLM-L6-v2, 384-d,
pgvector) ≥ **0.45**, (c) small category-context bonus. Top ≤6 kept
(`SKILL_MAX_RESULTS`) with score, `match_type` (EXACT/HYBRID/SEMANTIC) and
reason strings. **Nothing is forced**: no match → empty list + honest
`INSUFFICIENT_DATA` downstream (proven on 3 demo problems). Live: network →
Computer Networking 0.99; electrical → Electrical Maintenance 0.99.

## 4. Duplicate detection (semantic, admin-gated)

Each report embedded with MiniLM (384-d, `problem_embeddings`,
`source_text_hash` for staleness). Pair score =
**0.85 × cosine + 0.10 × location + 0.05 × category**; candidate ≥ **0.60**,
STRONG badge ≥ **0.82** (5 candidates max). Live: true paraphrase 0.8968/
final 0.9123 STRONG; distinct incidents 0.67–0.74 POSSIBLE. Admin must confirm
(join/merge cluster, member → DUPLICATE, canonical priority recount) or reject
(record kept, never silently re-offered). **No automatic destructive merge,
ever.** Canonical = oldest confirmed report.

## 5. Team recommendation (combination search, advisory)

Eligibility first: role SOLVER, AVAILABLE (not UNAVAILABLE), workload headroom,
has profile. Then team *combinations* (2–4 members, 12-candidate pool,
3 options) scored: coverage **50** + proficiency **20** + availability **10**
+ workload **10** + verified skills **5** + domain **5**. Not top-N
individuals — complementary coverage wins. Stored per-run with breakdown;
admin may accept or override (reason recorded, originals immutable). No
workload change at recommendation time.

## 6. Mentor recommendation (semantic + skills, advisory)

Eligibility like solvers (faculty profiles). Score: specialization **35**
(MiniLM cosine of specialization vs problem) + skill match **30** +
category **15** + availability **10** + workload **10**. Live: networks
professor ranked 46.16 for a WiFi outage — semantically correct. Admin
assigns finally, with override reasons.

## 7. Knowledge semantic search

Only CLOSED+verified problems publish: snapshot (title/summary/category/
root-cause/solution/testing/team+mentor names — **no reporter identity,
email, or internal notes**) + MiniLM embedding (`knowledge_embeddings`) +
skill links. Search modes: keyword, semantic (cosine, min **0.35**), hybrid
(0.75 semantic + 0.25 keyword), limit 10, category filters; `related` +
reporter-safe `related-solutions` reuse the same vectors. Tiny corpus ⇒ exact
scan (correct; no ANN index needed).

## 8. Human-in-the-loop (why the system is safe)

AI **never** makes a final institutional decision: admin corrects categories,
confirms every duplicate, picks teams/mentors (or records why not), closes
reports; mentors approve solutions; reporters verify resolutions. Every AI
output carries confidence/scores/reasons; failures render honestly
(`FAILED` states in UI) and never block reporting. This makes the system
explainable, auditable (append-only histories), and demo-safe.

## 9. Honest limitations

288-sample dev dataset; SAFETY_SECURITY (F1 0.0) and INFRASTRUCTURE (0.25)
weak; low confidences routine (0.2–0.5); MiniLM thresholds tuned on small
data; recommenders are deterministic heuristics, not learned rankers; no ANN
index (fine <100k vectors); demo dataset tiny. Stated, not hidden — the
human gates exist because of them.
