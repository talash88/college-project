# Step 8 — Student Team + Faculty Mentor Recommendations

**Status: Complete. Real data, deterministic teams, explainable 0–100 scores.
Advisory only: no assignment, no workload changes, no auto-anything.**

For each valid independent/canonical problem, CampusXolve AI now recommends up
to 3 student team options (evaluated as combinations, never top-N individuals)
and ranks eligible faculty mentors — all from real Step 6 required skills,
user proficiency/verification, availability, workload, department, and
specialization. Every score ships with its exact breakdown; explanations are
generated directly from score inputs (no LLM).

Steps 1–7 untouched in behavior: migrations `001`–`007` unmodified (verified
`001 → … → 008` chain), classifier/priority/skill/duplicate logic and tests
untouched. One project-wide learning applied: `users.role` and
`availability_status` columns are VARCHAR + check constraints (migration 002),
so Enum-typed SQL binds render a failing `::enum` cast under asyncpg — the new
eligibility queries cast the column to String (the reason existing
`status.in_(...)` queries only ever worked on the real `problem_status` enum).

## 1. Migration 008 state

- Revision `008`, down-revision `007`, head. `alembic upgrade head` clean.
- New tables: `team_recommendations` (+`run_id` grouping options per analysis
  run), `team_recommendation_members` (per-solver reasons), `mentor_recommendations`
  (one row per eligible mentor per run). Score range checks, indexes on
  `problem_id` / `run_id` / `created_at` / `mentor_user_id`, deliberate
  CASCADEs (recommendations die with their problem or user).
- `problems.team_recommendation_status` + `problems.mentor_recommendation_status`
  (`String(30)`: `NO_ELIGIBLE_CANDIDATES` is 23 chars — found by testing),
  with check constraints.
- New `problem_event_type` values: `TEAM_RECOMMENDATION_COMPLETED`,
  `MENTOR_RECOMMENDATION_COMPLETED` (append-only pattern, same as 007).

## 2. Student eligibility

`role = SOLVER`, `is_active`, StudentProfile exists,
`availability_status ∈ {AVAILABLE, LIMITED}`, `0 ≤ current_workload < max_workload`
(DB filters + Python belt-and-braces for inconsistent rows). Confirmed
DUPLICATE members get NO independent recommendation — the API returns the
canonical pointer (`Recommendation handled through canonical issue CX-…`);
canonical/independent reports are analyzed normally.

## 3. Team-size rules

`TEAM_MIN_SIZE = 2`, `TEAM_MAX_SIZE = 4`, `TEAM_ALLOW_SOLO = false` (default
collaborative; solo only if config allows AND one solver genuinely covers).
Sizes outside 2–4 are never produced. Exact ties prefer the smaller team, then
lower workload, then UUID order — fully deterministic, no randomness.

## 4. Team algorithm (combinations, not ranking)

Pre-rank solvers by solo score → cap pool at `TEAM_CANDIDATE_POOL = 12` →
evaluate every exact combination of sizes 2–4 (≤ 781 evaluations: 66 + 220 +
495) → sort by (−score, size, workload, UUIDs) → top
`TEAM_NUM_OPTIONS = 3` distinct teams (fewer if fewer exist — never padded).

## 5. Team score (0–100, recommendation score, NOT probability)

| Component | Weight | Design |
|---|---|---|
| Skill Coverage | 50 | relevance-weighted best-match strength per required skill (max over members — no double counting) |
| Skill Proficiency | 20 | mean raw proficiency factor of best matches |
| Availability | 10 | AVAILABLE 1.0 / LIMITED 0.5 mean |
| Workload Balance | 10 | mean spare fraction `1 − current/max` (0/3 beats 2/3) |
| Verified Skill Bonus | 5 | verified-exact 1.0 / unverified-or-partial 0.5 / none 0 |
| Domain/Department | 5 | 1.0 on genuine dept fit, neutral otherwise (never punishes) |

Per-skill match: exact `skill_id` → full proficiency factor; same-category →
0.30 × factor; else 0. Proficiency map: 1→0.20 … 5→1.00. Individual member
score = solo team score. Breakdown + per-skill best-member table persisted.

No robustness bonus was added (would break the 100 total) — documented choice.

## 6. Mentor algorithm

Eligibility mirrors students (`MENTOR` + FacultyProfile + reachable + spare
capacity). Score (0–100):

| Component | Weight | Design |
|---|---|---|
| Specialization Similarity | 35 | Sentence Transformer cosine, problem (title+desc+category+required skills) vs mentor (specialization+skills+dept+designation), stored separately too |
| Required Skill Match | 30 | relevance-weighted best proficiency, exact/category rule shared with teams |
| Category/Domain | 15 | recall of category tokens in specialization/dept tokens, affix-tolerant (`network` matches `networks`), generic tokens ignored |
| Availability | 10 | AVAILABLE 1.0 / LIMITED 0.5 |
| Workload | 10 | spare fraction |

Ranking is deterministic (−score, workload ratio, UUID). All eligible mentors
persisted per run (history + full ranking).

## 7. Real smoke outputs (live API, unaltered)

Model: `sentence-transformers/all-MiniLM-L6-v2` (existing). Versions:
`campusxolve-team-recommender-v1`, `campusxolve-mentor-recommender-v1`.

A. Network/WiFi — required: Computer Networking 0.99, Linux 0.99:

- Option 1: 67.97, coverage 52%, {Alex Chen, Jordan Kim [Networking, Linux], Priya Sharma};
  breakdown 26.0/16.0/8.33/8.89/3.75/5.0; missing [Computer Networking] (truthful: nobody holds it)
- Mentor Torres (Networks/Systems): 69.05 (spec 11.55, skill 30.0, cat 7.5, sem 0.33) >
  Mentor Johnson (AI/ML): 26.72

B. Web/UI — required: React 0.99, Responsive Web Design 0.5367:

- Option 1: 83.39, coverage 73.28%, {Alex Chen [React], Priya Sharma};
  breakdown 36.64/18.0/10.0/10.0/3.75/5.0; missing [Responsive Web Design]
- Mentors: Torres 33.11 vs Johnson 30.12 — honestly weak both ways (no web mentor seeded)

C. ML/NLP — required: Python 0.99, ML 0.95, NLP 0.95:

- Option 1: 100.0, coverage 100%, {Alex Chen, Priya Sharma [Python, ML, NLP]};
  breakdown 50.0/20.0/10.0/10.0/5.0/5.0; missing []
- Mentor Johnson: 65.91 (spec 15.91, skill 30.0, sem 0.4546) > Mentor Torres: 35.32

Seed workloads verified unchanged after all recommendations. Temp smoke data removed.

## 8. No-recommendation cases (truthful states)

- No Step 6 skills (e.g. pigeon-nesting report): `INSUFFICIENT_DATA` +
  "Insufficient skill requirements for confident recommendation." (nothing fabricated)
- No eligible solvers/mentors: `NO_ELIGIBLE_CANDIDATES` + empty lists
- Duplicate member: canonical pointer, no independent rows
- Any failure: `FAILED`, report + classification + priority + skills + duplicates intact

## 9. Pipeline & APIs

Create → classification → priority → skills → duplicates → **team → mentor**
(each failure-safe; statuses `NOT_RUN/PROCESSING/COMPLETED/
NO_ELIGIBLE_CANDIDATES/INSUFFICIENT_DATA/FAILED` on the problem).

- `GET /problems/{id}/team-recommendations` (+ `/history`)
- `GET /problems/{id}/mentor-recommendations` (+ `/history`)
- `POST /admin/problems/{id}/recommendations/team/recalculate`
- `POST /admin/problems/{id}/recommendations/mentor/recalculate`
  (admin-only; appends runs; reporters 403, strangers 404, anonymous 401)
- Reporters: names, covered skills, scores, availability badges — no user IDs,
  emails, identifiers, or workload numbers. Admins: full diagnostics.

## 10. Frontend

Problem detail: Recommended Student Team (option cards, top pick highlighted,
score/coverage bars, initial avatars, skill chips with proficiency labels,
expandable "Why recommended?", missing skills, skeleton/empty/error+retry) and
Recommended Faculty Mentor (ranked cards, score bars, skill chips, semantic +
breakdown for admins). Admin: recalculate buttons + disabled
"Assign (next step)" placeholders — no fake working buttons. `lint`,
`type-check`, `build` green.

## 11. Tests & quality

- `pytest tests/`: **156 passed** (33 new: 14 pure team math, 4 pure mentor
  math, 15 API incl. complementary>redundant, exclusions, penalties,
  relevance, verified bonus, sizes, determinism, ordering, duplicates,
  permissions, workload freeze, history).
- `ruff check .` clean, `mypy app/` clean (90 files), `alembic upgrade head`
  at `008`, frontend lint/typecheck/build green. Steps 1–7 suites all green.

## 12. Bugs found by testing (fixed)

1. `TeamOptionResponse.model_validate` 500 (ORM members need explicit builders).
2. VARCHAR-vs-enum SQL comparisons (`users.role`, availability) — String-cast fix.
3. Mentor skill-match ignored the category-partial discount (used raw proficiency).
4. Category overlap never fired (exact-token Jaccard; `networks` ≠ `network`) — affix-tolerant recall.
5. Status column width: `NO_ELIGIBLE_CANDIDATES` needs String(30).
6. Async lazy-load (`MissingGreenlet`) in tests: eager-load profiles.
7. `AsyncSession.expire_all` is sync (test fix).

## 13. Limitations

- Only 3 seeded solvers / 2 seeded mentors: options saturate quickly; a farmscale pool would exercise the pool cap (12) more meaningfully.
- Category component inherits classifier quirks (ML text → IT_NETWORK).
- Partial (category) coverage lists a skill as both "covered (support)" and "missing" when strength < 0.5 — by design, could be surfaced better.
- `test_models.py::test_relationships` still commits `rel_*` users (pre-existing); Step 8 tests clean them in a fixture.
- Full suite is slower (mentor semantic encoding per problem; ~20s for the Step 8 module).

## 14. Not started (Step 9+)

Step 9 (approval/assignment/tasks/workload changes) has NOT started. No assign
buttons, no task creation, no workload increments exist anywhere.

## Reproduce

```bash
cd backend
python -m alembic upgrade head
python -m pytest tests/ -v
python -m ruff check . && python -m mypy app/
python scripts/smoke_recommendations.py
cd ../frontend
npm run lint && npm run type-check && npm run build
```
