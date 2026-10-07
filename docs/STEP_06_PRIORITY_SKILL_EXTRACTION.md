# Step 6 — Explainable Priority Scoring + Real Required-Skill Extraction

**Status: Complete. No random values, no hardcoded priorities, no fake skills,
no external LLM APIs.**

Every problem now receives a transparent weighted priority analysis and a
hybrid (exact-phrase + Sentence-BERT) required-skill analysis, each with
independent status, full audit history, and human-readable reasons generated
directly from scoring inputs.

Steps 1–5 untouched in behavior: migrations `001`–`005` unmodified, Step 5
classifier artifacts/metrics untouched (no retraining), all prior tests pass
(two Step 4 assertions evolved from "AI stays null" to "real analyses present").

## 1. PRIORITY

### Formula (campusxolve-priority-v1, score natively 0–100)

| Component | Max | Design |
|---|---|---|
| Severity / risk | 30 | Tiered lexicon hits (emergency 15, hazard 12, disruption 8, degradation 4), one hit per lexicon entry, capped |
| Affected people | 25 | Monotonic buckets: 1–5→5, 6–20→10, 21–50→15, 51–100→20, 101–500→23, 500+→25; NULL→0 ("not provided") |
| Pending age | 20 | Real timestamps: <1d→2, 1–3d→6, 4–7d→10, 8–14d→15, >14d→20; terminal statuses freeze at 0 |
| Category context | 15 | Admin-final else AI-predicted (SAFETY 12 … LIBRARY 3, OTHER 2, none 0); capped, never dominant |
| Duplicate impact | 10 | **Always 0 in Step 6** — "Duplicate detection not available yet (Step 7)" |

Levels: 0–29 LOW, 30–54 MEDIUM, 55–79 HIGH, 80–100 CRITICAL (env-tunable via
`PRIORITY_*_MAX`). Every component exposes raw value, contribution, max and a
generated reason (`+ 20: Approximately 100 people are affected.`); reasons are
assembled from components, never LLM-invented.

### Risk vocabulary strategy
Phrase-aware, case-insensitive matching over title+description with a
3-token negation window (`no/not/never/without/none` + `n't` suppress the hit),
so "there is no fire" does not score like "there is a fire" (tested).
Limitation (documented): window heuristic, no parsing — "no smoke, but fire
elsewhere" style sentences can misfire; direct text signals complement (not
replace) the imperfect classifier, especially for SAFETY_SECURITY.

### Age mapping
Timezone-aware `(now - submitted_at)`; terminal (RESOLVED/CLOSED/REJECTED/
DUPLICATE/WITHDRAWN) reports freeze at 0 — resolved reports never escalate.

### Real priority smoke outputs (live API, unaltered)
- Minor paint scratch, 1 affected, fresh → **7 LOW** (severity 0, affected 5, age 2)
- WiFi outage exams, 400 affected → **41 MEDIUM** (outage +8, affected 23, age 2, IT +8)
- Sparking panel + smoke, 120 affected, 5-day-old equivalent → **57 HIGH**
  (severity 27, affected 23, age 10–20, category ≤10)
- Broken bench, unknown affected → **12 LOW** (affected 0, "not provided" recorded)
- Fresh-report ceiling noted honestly: CRITICAL needs age accumulation
  (e.g. 27+25+20+10=82 for an old severe report).

## 2. SKILL EXTRACTION

### Hybrid architecture
Exact normalized phrase matching (word boundaries, longest-first, generic
single words like "design"/"system" excluded) + Sentence-BERT cosine over
pgvector-stored embeddings + 0.05 category bonus.
**Formula:** `score = min(max(exact ? 0.95, semantic) + bonus, 0.99)`;
match_type EXACT/SEMANTIC/HYBRID; keep iff score ≥ 0.45
(`SKILL_SIMILARITY_THRESHOLD`), max 6 (`SKILL_MAX_RESULTS`), ranked desc.
Called "match/relevance score", never "confidence". Below threshold → empty
list + COMPLETED status ("No sufficiently relevant required skills").

### Sentence Transformer
`sentence-transformers/all-MiniLM-L6-v2` (384-dim, normalized), singleton,
MPS/CPU, never CUDA-assumed, never reloaded per request. The DistilBERT
classifier is NOT abused as an embedder.

### Taxonomy & representations
46 active skills. Representation = name + category + description + controlled
aliases + a few complaint-context phrases (embedding-only, never exact-match).
`usable_phrases()` drops generic single words for exact matching.

### Embeddings (pgvector)
`skill_embeddings(skill_id, model_name, model_version, embedding VECTOR(384))`,
unique `(skill_id, model_version)`. `scripts/build_skill_embeddings.py` is
idempotent (upsert; verified 46 rows, re-run adds none). Version
`campusxolve-skill-embeddings-v1`; extractor `campusxolve-skill-extractor-v1`.

### Real unseen skill outputs (live API, unaltered)
- "wireless connection drops … programming lab" → **Computer Networking 0.5635 SEMANTIC**
- "portal unusable on mobile" → **Responsive Web Design 0.5275 SEMANTIC**
- "security camera stopped recording" → **CCTV Systems 0.99 EXACT**
- "exposed electrical wires near staircase" → **Electrical Maintenance 0.99 EXACT**
- "washroom not cleaned for days" → **no skills** (correctly empty)
- Task example (WiFi lab, 60 students) → **Computer Networking 0.99 HYBRID**;
  sysadmin/Linux not forced (only 1 strong match — truthful).
- Cleanliness complaint returns zero software skills (tested).

### Limitations
Small taxonomy gaps (e.g. transport → often legitimately empty); threshold and
aliases are tuned, not learned; semantic model is general-purpose English.

## 3. Pipeline, APIs, database
Create: persist → classify → priority → skills, each independently guarded;
any failure leaves the report SUBMITTED with truthful per-subsystem status
(NOT_RUN/COMPLETED/FAILED). History tables
(`problem_priority_analyses` with JSONB details, `problem_skill_analyses` +
`problem_required_skills` unique per analysis+skill); problem caches latest
score/level/statuses. Migration `006_priority_and_skills` verified
`001→…→006`. Owner endpoints `GET …/priority`, `GET …/required-skills`;
admin `POST …/priority/recalculate`, `POST …/skills/reanalyze` (optional
reason); reporters can never set scores/skills.

## 4. Frontend
Detail page: Priority (level badge, x/100, Why-list, expandable per-component
breakdown incl. duplicate 0 note, algorithm + timestamp, admin Recalculate)
and Required Skills (name, category, %, match-type badge, reason, empty state,
admin Re-analyze). Creation success shows ticket + priority + skills.
No teams/recommendations.

## 5. Tests & quality
`tests/test_priority.py` (9 engine unit + 3 API) and `tests/test_skills.py`
(4 matcher unit + 6 API incl. embedding coverage/idempotency): ranges, levels,
monotonicity, terminal freeze, negation, unknown-affected, duplicate-zero,
permissions, history, failure safety. **Full suite: 105 passed.** Ruff clean,
mypy strict clean (75 files; documented stub shims for numpy-family stubs),
ESLint/tsc/build green. Step 1–5 regression green.

## 6. Bugs found by testing (fixed)
VARCHAR-vs-native-enum (solved in Step 5 pattern), E2E smoke data polluting
dev DB (cleaned; test-specific filters added), Step 4 "AI null" assertions
evolved, embedding version mismatch, downgrade wiping embedding rows
(rebuilt), stale-relationship staleness handled via refresh.

## 7. Not started (Step 7+)
Duplicate detection/clustering, team/mentor recommendation, assignment,
tasks, notifications, verification, knowledge base, analytics.

## Reproduce
```bash
python3 scripts/build_skill_embeddings.py
python3 -m pytest tests/ -q
```
