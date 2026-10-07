# Step 13 — Real Analytics + Admin Intelligence Dashboard

Descriptive, explainable operational intelligence for admins. No predictions,
no fabricated values, no deployment changes. Migration head stays **012**
(no new migration: everything derives from existing tables).

## 1. Pre-existing analytics work

None, except the disabled sidebar placeholder (`Analytics → Soon`). No chart
library in the frontend (Next.js + React + Axios + Tailwind only). Charts are
hand-rolled SVG (no new dependency).

## 2. Analytics definitions

- **Open** = SUBMITTED, UNDER_REVIEW, APPROVED, ASSIGNED, IN_PROGRESS,
  AWAITING_VERIFICATION. Terminal statuses (RESOLVED, CLOSED, REJECTED,
  DUPLICATE, WITHDRAWN) are never open.
- **Category** = latest classification's `final_category`, else its
  `predicted_category`, else `UNCLASSIFIED` (explicit, never dropped).
- **Resolution duration** = `resolved_at` (else `closed_at`) minus
  `submitted_at`, only for RESOLVED/CLOSED rows with both timestamps.
- **Duplicate reduction ratio** = confirmed-DUPLICATE problems / all problems.
- **Avoided assignments** = confirmed cluster members with no assignment row
  (no invented hours/money saved).
- **Skill demand** = latest COMPLETED skill analysis per problem only
  (history rows never double-counted): distinct problems + avg relevance.
- **Overdue** (UTC, query time) = unfinished task (TODO/IN_PROGRESS/BLOCKED)
  with `due_date` past, or unfinished milestone (PLANNED/IN_PROGRESS) with
  `target_date` past. Upcoming = target within 7 days.
- **Override rate** = admin-composed (override flag) / all assignments;
  classification override = `final_category` differs from prediction among
  reviewed rows (labeled as human disagreement, never "AI error rate").

## 3. Time range behavior

`preset` (7d/30d/90d/1y/all) or explicit `date_from/date_to` (custom dates win).
Problem metrics scope by `submitted_at`. Trends bucket reported by
`submitted_at`, resolved by `resolved_at` (else `closed_at`); granularity auto
(day ≤ 62 days, else week); zero-filled buckets for chart continuity.

## 4. Resolution formulas

AVG/MIN/MAX over `extract(epoch, ...)`; MEDIAN and P90 via
`percentile_cont(...).within_group(...)`. Open problems excluded by
construction.

## 5. Duplicate formulas

Confirmed problems, active clusters (members > 0), avg/largest cluster size,
PENDING/CONFIRMED/REJECTED candidate counts, confirmation rate
(confirmed / decided, null when undecided), reduction ratio, avoided
assignments. Rejected candidates never count as duplicates.

## 6. Skill-demand logic

See §2. Ranked by distinct-problem count; relevance averaged.

## 7. Workload logic

Solver/mentor availability counts, used/capacity sums, utilization ratio,
current-workload histogram, busiest-tables (display names only, top 10 by
load). Framed as capacity, never ranked as best/worst.

## 8. AI metric distinction

- **Stored offline evaluation** (read from
  `ml/artifacts/problem_classifier/{metrics,metadata}.json`, never
  recalculated): version, base model, dataset sizes (201/43/44), accuracy
  **0.6591**, macro F1 **0.63**, weighted F1 **0.644**, threshold 0.60,
  per-class F1 sorted weakest-first (SAFETY_SECURITY 0.0, INFRASTRUCTURE 0.25).
- **Live operational statistics**: classification counts by status,
  low-confidence rate, failures, reviewed/override counts, pending candidates.
- UI labels the former "Development Evaluation Dataset — not production
  accuracy" with helper text.

## 9. SQL/query approach

`COUNT/GROUP BY/AVG/MIN/MAX`, window `row_number()` for latest-per-problem
(classification, skill analysis), `DISTINCT ON`-free portable constructs,
`percentile_cont`, bounded `LIMIT` detail rows, eager loading where object
graphs are read. Median/P90 in-database. No Redis; no caching (dashboard
~0.07–0.10s on dev data).

## 10. Privacy

Aggregates everywhere; only admin-visible display names in workload tables
and ticket/title links. CSVs contain no emails, IDs, comments, or tokens.
Regression tests assert banned markers across dashboard JSON, CSVs, and names.

## 11. API

All `require_admin` (401 unauthenticated, 403 non-admin — tested for all roles):

- `GET /api/v1/admin/analytics/dashboard` (one coherent snapshot + filters)
- `GET /api/v1/admin/analytics/trends` (granularity drilldown)
- `GET /api/v1/admin/analytics/export/problems.csv` (respects filters)
- `GET /api/v1/admin/analytics/export/skills.csv`

Filters (`preset|date_from|date_to|category|location`) apply only where
semantically valid (documented per section in code).

## 12. CSV

`text/csv` downloads with exact headers; problems CSV respects filters;
skills CSV aggregates demand. Tested: headers, row counts, escaping via
`csv` module, content-type, empty-filter header-only output, no sensitive
columns.

## 13. Frontend (`/analytics`, ADMIN only)

Header + CSV export buttons; preset/custom/category/location filter bar;
8 KPI cards; Reported-vs-Resolved SVG trend; SVG bar charts (category,
priority, locations-as-cards, skills); resolution stats; high/critical table
(linked); duplicates panel; workload tables; assignment/override panel; AI
Health section; operations watch; knowledge panel. Non-admin nav hides the
item; direct URL renders the 403 page (browser-verified). Empty filters render
zeros without errors. 390px mobile: no overflow, stacked layout. Contrast uses
the fixed `.input-field` system (verified dark mode).

## 14. Tests (`tests/test_analytics.py`, 20 tests)

Access matrix (5 paths × admin/reporter/solver/mentor/anon) · exact overview
counts via location filter · open-definition self-consistency · trend buckets
+ zero-fill · category percentages · location normalization ("K13 Library" /
" k13 library " / "K13 LIBRARY" group to 3) · priority shape · single-problem
resolution exactness (avg=median=min=max=p90) · override deltas from real
flows · verification + reopen-rate math · skill no-double-count after
reanalyze · workload aggregates + name privacy · duplicate confirm deltas ·
knowledge publication delta · overdue/blocked/upcoming from real dated rows ·
model quality exact artifact values · privacy markers · empty-filter zeros ·
CSV headers/rows/filters/escaping · perf with 25 bulk rows.

## 15. Performance timings (measured, not claimed)

- Dev dashboard (6 problems): **~0.07s**
- Test dashboard (+25 bulk rows): **0.10s**
- Trends 90d: **0.01s**
- Perf test asserts dashboard + trends < 8s with bulk rows.

## 16. Limitations

- Small demo dataset: some panels read "None yet" honestly (no fabrication).
- Category/location filters scope problem-based sections; global counts
  (clusters, knowledge, candidates) are intentionally unscoped.
- Trends resolve by `resolved_at` else `closed_at` (documented choice).
- No caching, no background jobs, no PDF export, no forecasting.
- Analytics explicitly out of scope for non-admin roles.
