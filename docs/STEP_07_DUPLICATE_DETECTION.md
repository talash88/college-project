# Step 7 — Semantic Duplicate Detection & Clusters

**Status: Complete. Real embeddings, real pgvector search, real hybrid scoring.
No auto-merge ever: even a 0.99 match stays a suggestion until an admin confirms it.**

Every report gets a 384-dimensional semantic embedding at creation (and on
embedding-relevant edits). New reports are matched against existing ones with
pgvector cosine search plus location/category support; qualifying pairs become
PENDING suggestions. Admins confirm (cluster join/merge, member status,
canonical priority recount) or reject (record preserved, never re-offered).
Reporters only ever see ticket/title/status of counterparts — never another
reporter's identity, attachments, or internal notes.

Steps 1–6 untouched in behavior: migrations `001`–`006` unmodified, Step 5
classifier and Step 6 scorer/configs untouched. One deliberate Step 6
integration fix: admin priority recalculation now resolves the real
confirmed-duplicate count instead of resetting it to zero (see §7).

## 1. What already existed vs what was finished

The previous session left behind (verified by inspection, not recreated):

- Migration `007` (embeddings, candidates, clusters, members, problems
  duplicate-status/canonical columns, new activity event values)
- `ProblemEmbedding`, `ProblemDuplicateCandidate`, `DuplicateCluster`,
  `DuplicateClusterMember` models
- `DuplicateService` (embeddings, analysis, confirm/reject/cluster logic)
- Priority `duplicate_count` plumbing + recount on confirm
- Owner (`GET /problems/{id}/duplicates`) and admin
  (reanalyze/confirm/reject/clusters) APIs
- `tests/test_duplicates.py` (12 passing, 4 failing)
- `scripts/backfill_problem_embeddings.py` and
  `scripts/calibrate_duplicate_thresholds.py` drafts
- No frontend duplicate UI, no cluster pages, no Step 7 doc

Finished in this session (no working logic rewritten):

1. **Reanalysis crash (IntegrityError):** re-running analysis marked old
   PENDING rows STALE, then re-inserted the same order-independent pair →
   unique-constraint violation. Analysis now revives the STALE row in place,
   only the report's *own* outdated suggestions go STALE, and
   REJECTED/CONFIRMED pairs are never silently re-offered.
2. **Concurrent-creation race:** two simultaneous analyses could insert the
   same pair (broke `test_ticket_numbers_concurrent_safe`). The pair upsert
   now runs in a savepoint; the loser skips without poisoning the report
   transaction.
3. **Cluster-merge data loss (critical):** merging moved members to the
   surviving cluster, then `session.delete(drop)` cascade-deleted the moved
   rows through the drop cluster's stale in-memory collection — the merged
   cluster silently lost members. The drop cluster's member collection is now
   reloaded after the move, before deletion.
4. **Owner visibility:** owners saw bidirectional pairs, so the first report
   showed suggestions triggered by later reports. Owners now see only PENDING
   suggestions triggered by their own report's analysis; admins keep the full
   bidirectional + decided view.
5. **Priority recalc wipe:** admin priority recalculation passed
   `duplicate_count=0`, erasing the canonical's confirmed-duplicate
   contribution. `analyze_problem_id` now resolves the real confirmed count
   from the cluster when no explicit count is passed (new regression test).
6. Reporter duplicate section + confirmed-duplicate banner, admin review
   controls, `/admin/duplicates` list + cluster detail pages, nav entry.
7. Backfill processed/skipped/failed counts; calibration + smoke scripts with
   real measured numbers; this doc; README roadmap.

## 2. Migration 007 state

- Revision `007`, down-revision `006`, head. `alembic upgrade head` clean.
- New tables: `problem_embeddings` (pgvector 384, unique per
  problem+model-version), `problem_duplicate_candidates` (order-independent
  unique pair, no-self + 0–1 range checks), `duplicate_clusters`
  (`DC-NNNN` numbering via sequence), `duplicate_cluster_members` (one
  membership per problem, one canonical per cluster via partial unique index).
- `problems.duplicate_status` (NOT_RUN/PROCESSING/COMPLETED/FAILED/NO_MATCHES/
  POSSIBLE_DUPLICATES) + `problems.canonical_problem_id` (self-FK, SET NULL).
- New `problem_event_type` values: DUPLICATE_ANALYSIS_COMPLETED,
  DUPLICATE_CONFIRMED, DUPLICATE_REJECTED, JOINED_DUPLICATE_CLUSTER,
  DUPLICATE_CLUSTER_MERGED.

## 3. Embeddings

- Model: `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, normalized.
- Version: `campusxolve-problem-embedding-v1` (config `PROBLEM_EMBEDDING_VERSION`).
- Embedded text: title + description + location fields + classifier category
  (`format_duplicate_text`); no reporter identity, tickets, or timestamps.
- Idempotent: SHA-256 source-text hash stored per row; unchanged text reuses
  the row, edits recompute it (one row per problem+version).

## 4. Thresholds & hybrid formula

- `DUPLICATE_CANDIDATE_THRESHOLD = 0.60` (semantic cosine floor for a suggestion)
- `DUPLICATE_STRONG_THRESHOLD = 0.82` (config-only today: recorded for future
  admin hinting; nothing auto-merges — informational, not enforced)
- `DUPLICATE_CANDIDATE_LIMIT = 5` new suggestions per analysis
- `final = 0.85·semantic + 0.10·location + 0.05·category`, rounded to 4 decimals
  (algorithm `campusxolve-duplicate-detector-v1`). Semantic dominates by design;
  location is Jaccard overlap of informative tokens (generic tokens such as
  "block"/"main"/"hall" ignored); category is 1.0 on classifier agreement else
  0.0 and never vetoes.

## 5. Real development calibration (measured, not invented)

`python3 scripts/calibrate_duplicate_thresholds.py` — real model outputs:

Short title-only pairs:

| pair | kind | sem | final |
|---|---|---|---|
| wifi-paraphrase | positive | 0.639 | 0.550 |
| cctv-paraphrase | positive | 0.412 | 0.350 |
| water-paraphrase | positive | 0.814 | 0.729 |
| lab-wifi-paraphrase | positive | 0.468 | 0.421 |
| library-wifi-vs-water | negative | 0.290 | 0.255 |
| lab-projector-vs-network | negative | 0.395 | 0.366 |
| hostel-clean-vs-electrical | negative | 0.443 | 0.383 |
| transport-vs-mess | negative | 0.116 | 0.098 |
| sparking-vs-leak | negative | 0.102 | 0.105 |
| wifi-library-vs-hostel | borderline | 0.496 | 0.430 |
| library-wifi-vs-light | hard | 0.387 | 0.337 |
| gate-cctv-vs-streetlight | hard | 0.437 | 0.405 |

Full report-style texts (what the pipeline actually embeds):

| pair | kind | sem | loc | final |
|---|---|---|---|---|
| wifi-full-positive | positive | 0.725 | 0.33 | 0.700 |
| cctv-full-positive | positive | 0.601 | 0.00 | 0.561 |
| library-wifi-vs-water-full | negative | 0.387 | 0.50 | 0.379 |
| hostel-clean-vs-elec-full | negative | 0.530 | 1.00 | 0.550 |

Reading: with pipeline-style texts, positives (0.601–0.725+) clear 0.60 while
same-location negatives stay below (0.530 max) — but the margin is thin, and
title-only paraphrases (cctv 0.412) would miss. This is development calibration
on a tiny hand-built set, NOT production-grade tuning. Threshold 0.60 kept.

## 6. Real smoke tests (measured, live)

`python3 scripts/smoke_duplicate_detection.py` — required pairs, full texts:

| pair | kind | sem | loc | cat | final | candidate |
|---|---|---|---|---|---|---|
| library-wifi-vs-internet | positive | 0.751 | 0.33 | 1.0 | 0.721 | yes |
| main-gate-cctv-vs-entrance-cam | positive | 0.622 | 0.00 | 1.0 | 0.578 | yes |
| cse-water-vs-drinking-station | positive | 0.837 | 1.00 | 1.0 | 0.861 | yes |
| library-wifi-vs-light | negative | 0.447 | 1.00 | 0.0 | 0.480 | no |
| lab-internet-vs-projector | negative | 0.402 | 1.00 | 0.0 | 0.441 | no |

The hard negatives share the exact location (support 1.00) yet stay below
threshold — semantic similarity decides, as designed.

Live end-to-end (API, unaltered): water paraphrases produced candidate
`sem=0.8021 loc=1.0 cat=1.0 final=0.8318 PENDING`; admin confirm created
cluster `DC-0041` with 2 members; member status → DUPLICATE with canonical
link `CX-2026-001279`.

## 7. Priority integration (real before/after)

Same live run, canonical report's priority components:

- BEFORE confirmation: `score=4.0`, `duplicate_impact {contribution=0, raw=0}`
  (a PENDING suggestion moves nothing).
- AFTER admin confirmation: `score=6.0`,
  `duplicate_impact {contribution=2, raw=1}` (+2 per confirmed duplicate,
  appended as a new audit row — history preserved).
- Rejection leaves priority untouched; admin recalculation preserves the
  contribution (regression-tested).

## 8. Cluster logic & canonical policy

- Confirm with neither report clustered → new `DC-NNNN` cluster; oldest report
  (by submitted_at) is canonical, the other becomes DUPLICATE pointing at it.
- Confirm with one side clustered → newcomer joins; existing canonical preserved.
- Confirm across two clusters → merge into the oldest cluster; oldest member
  overall becomes canonical; dropped cluster deleted; every non-canonical
  member points at the surviving canonical.
- Reverse-direction PENDING rows for the same pair are decided together.
- Priority of the canonical is recounted with the real confirmed count.
- Activity events recorded on both reports for every decision.

## 9. Pipeline, APIs, backfill

- Create → classify → priority (count 0) → skills → duplicate analysis; edit of
  title/description/location → embedding refresh + reanalysis. Every subsystem
  fails independently; the report is never lost.
- Owner: `GET /problems/{id}/duplicates` (own PENDING suggestions + cluster +
  safe canonical summary). Admin: reanalyze, confirm, reject, list/get clusters.
- Backfill `scripts/backfill_problem_embeddings.py [--analyze] [--limit N]`:
  only reports missing the current embedding, safe rerun, counts reported.
  Measured: run 1 `processed=2 skipped=0 failed=0`; run 2
  `processed=0 skipped=0 failed=0` (idempotent); `--analyze` run
  `processed=2 analyzed=2 analyze_failed=0`.

## 10. Frontend

- Report page: `DuplicatesSection` — Analyzing / No similar issue found /
  Possible similar issue found / Analysis failed states; candidate cards with
  ticket, title, status, semantic similarity, final match score (no reporter
  identity, no links for reporters since counterparts aren't visible to them).
- Confirmed duplicates: purple banner "This report has been linked to an
  existing campus issue." with canonical ticket/title/status/location.
- Admin on the same page: per-candidate semantic/location/category/final +
  decision, linked titles, optional review note, Confirm Duplicate / Reject
  Match / Re-analyze — all persisted to the backend.
- `/admin/duplicates`: cluster number, canonical ticket, member count,
  canonical status, created date. `/admin/duplicates/[id]`: canonical issue,
  members (linked, canonical badge, reporter names), duplicate-event decision
  history from the canonical report's activity. Nav: Administration →
  Duplicates. `npm run lint`, `type-check`, `build` green.

## 11. Tests & quality

- `python3 -m pytest tests/ -v`: **122 passed** (17 duplicate tests incl. new
  recalc-preservation regression test; Steps 1–6 suites all green), run twice.
- `python3 -m ruff check .`: clean. `python3 -m mypy app/`: clean (81 files).
- `python3 -m alembic upgrade head`: at `007` (head), no-op.
- Frontend `npm run lint` / `type-check` / `build`: green (new
  `/admin/duplicates`, `/admin/duplicates/[id]` routes in build output).

## 12. Bugs found by testing (fixed)

1. Reanalysis `IntegrityError` on the order-independent pair constraint.
2. Concurrent-creation pair-insert race (also broke a Step 4 ticket test).
3. Cluster merge silently dropping moved members via delete-orphan cascade.
4. Owner visibility showing other reports' triggered suggestions.
5. Admin priority recalculation zeroing the duplicate contribution.

## 13. Limitations

- Thresholds are development calibration on ~16 hand-built pairs; the
  positive/negative margin near 0.60 is thin (cctv 0.601–0.622).
- Title-only short texts score lower than full report texts; very terse
  reports may miss paraphrases.
- Strong-match threshold (0.82) recorded but not enforced anywhere yet.
- Owner suggestions are trigger-directional: reanalysis by another party can
  move a suggestion out of an owner's view (status stays consistent).
- Tests run against the shared development database; member-less clusters from
  cascade cleanup are filtered in cluster assertions.
- `test_models.py::test_relationships` commits `rel_*` users without cleanup
  (pre-existing, harmless, out of scope).

## 14. Not started (Step 8+)

Step 8 (Admin Workflow & Task Management) has NOT started. No assignment,
scheduling, team, or Step 8 API/UI work is included here.

## Reproduce

```bash
cd backend
python -m alembic upgrade head
python -m pytest tests/ -v
python -m ruff check . && python -m mypy app/
python scripts/calibrate_duplicate_thresholds.py
python scripts/smoke_duplicate_detection.py
python scripts/backfill_problem_embeddings.py        # rerun → processed=0
cd ../frontend
npm run lint && npm run type-check && npm run build
```
