# Step 12 — Knowledge Repository + Semantic Search + Related Solved Problems

Institutional memory for CampusXolve AI: verified solved problems become
reusable knowledge. No Analytics in this step.

## 1. Pre-existing Step 12 work

None, except the disabled sidebar placeholder (`Knowledge Repository → Soon`
in `navigation.tsx`). No models, routes, services, or components existed.
Everything below is new; Steps 1–11 and stabilization fixes untouched
(migrations 001–011 unmodified; head is now **012**).

## 2. Publication eligibility (strict rule)

An official knowledge article is created ONLY when ALL hold:

- `problems.status = CLOSED`
- a final solution submission exists (latest revision)
- that final revision has a mentor review with decision `APPROVED`
- a reporter verification with decision `RESOLVED` points at that final revision
- `canonical_problem_id IS NULL` (confirmed DUPLICATE members never publish;
  only the canonical closed issue may publish)

Never published: SUBMITTED, UNDER_REVIEW, APPROVED, ASSIGNED, IN_PROGRESS,
AWAITING_VERIFICATION, REJECTED, WITHDRAWN, DUPLICATE members.

## 3. Snapshot strategy

`knowledge_entries` stores a publication snapshot (title, description,
category, location, root cause, solution, work, testing, deployment notes,
limitations, duration, team display names, mentor name/designation, shareable
evidence list) plus FKs to the source problem and final submission. Published
content never silently changes: re-embedding/republish only happens through
explicit publish/retry/unarchive flows, each audited in the activity timeline.

Missing facts are never invented: nullable source fields stay null.

## 4. Schema (migration 012)

- `knowledge_entries` (unique `problem_id`, `public_id` like `KB-000001` from
  sequence `knowledge_entry_number_seq`, status PENDING/PUBLISHED/FAILED/ARCHIVED)
- `knowledge_entry_skills` (entry ↔ Skill taxonomy, relevance score)
- `knowledge_embeddings` (one `VECTOR(384)` row per entry + model/version/hash)
- `problem_work_attachments.is_knowledge_shareable` (default false)
- 4 new `problem_event_type` values (append-only pattern)
- Indexes on problem_id/status/published_at/category/skill/entry links.
  Vectors: exact pgvector scan, no HNSW/IVFFlat — correct at college scale
  (tens/hundreds of articles); revisit past ~100k rows.

## 5. Privacy

List/detail/related responses contain only: titles, texts, category, location,
skill names, durations, dates, team display names, mentor name+designation,
explicitly shareable evidence. Never: emails, student/employee IDs, workloads,
profiles, internal notes, reporter identity, tokens. Covered by a dedicated
regression test asserting banned markers across 4 responses.

## 6. Safe evidence policy

Default private. A work file reaches the repository only if BOTH: referenced
by the final solution's `evidence_attachment_ids` AND flagged
`is_knowledge_shareable` (set at upload or via `PATCH .../shareable`, by
uploader/mentor/admin only). Downloads re-verify the flag live (revocable) and
serve bytes through the existing storage backend to authenticated users.

## 7. Embeddings

Shared singleton `sentence-transformers/all-MiniLM-L6-v2` (no second model),
384 dims, L2-normalized. Version tag `campusxolve-knowledge-embedding-v1`.
Source text (deterministic, identities excluded):

```
Title / Problem / Category / Location / Root Cause / Solution /
Work Performed / Skills
```

`sha256` of this text drives idempotent re-embedding (one row per entry).

## 8. Search modes and ranking (deterministic)

- `keyword_score` = matched/total over lowercase alphanumeric tokens (len ≥ 2);
  a term matches as a case-insensitive substring. Multi-term = AND of per-term
  OR-groups across title/summary/root/solution/work.
- `semantic_similarity` = cosine via pgvector (normalized both sides).
- `HYBRID/ALL = 0.75 * semantic + 0.25 * keyword`
  (`KNOWLEDGE_HYBRID_SEMANTIC_WEIGHT/_KEYWORD_WEIGHT`); candidates kept when
  semantic ≥ threshold OR keyword > 0. `SEMANTIC` keeps ≥ threshold.
  `KEYWORD` keeps keyword > 0. Empty query → newest first.
- Sorts: relevance (score, then newest), newest, oldest. Pagination (cap 50).

## 9. Threshold and limits

`KNOWLEDGE_SEMANTIC_MIN_SCORE = 0.35`, `KNOWLEDGE_SEARCH_LIMIT = 10`
(default page size). Calibrated with real smoke runs (below): true paraphrase
matches scored 0.46–0.78, unrelated topics fell below 0.35 and were excluded.

## 10. Related solutions

- `GET /knowledge/{id}/related`: top-5 by entry-embedding similarity, never
  itself, published only (threshold not applied; honest ranking with scores).
- `GET /problems/{id}/related-solutions`: embeds the open problem (same
  formatter, solution sections omitted) and searches published entries.
  Visibility first (`get_visible_problem`): outsiders get 404. Informational
  only — never marks duplicates, never mutates state.

## 11. Auto-publication

`SolutionService.close_problem` commits CLOSED, then best-effort
`KnowledgeService.publish_for_problem`. Close stays valid if publication
fails (FAILED row + activity; admin retries). No fake entries.

## 12. Backfill

`scripts/backfill_knowledge_repository.py` (`--dry-run` supported): publishes
CLOSED problems lacking entries through the same service. Idempotent.
Dev runs: `processed=0 published=0 skipped=0 failed=0` twice in a row
(everything already auto-published; second pass creates nothing).

## 13. Failure handling

Model/embedding outage → FAILED entry (retryable), close unaffected; search in
SEMANTIC mode returns `semantic_available: false` + honest error while
KEYWORD keeps working (tested with a simulated outage).

## 14. Frontend

- Sidebar: Knowledge Repository enabled for all roles; Knowledge Admin for admins.
- `/knowledge`: search + mode/category/skill/location/sort + pagination +
  empty state ("No solved problems have been published to the Knowledge
  Repository yet."). Contrast-safe via the global `.input-field` fix.
- `/knowledge/[id]`: Problem / Root Cause / Verified Solution / Work /
  Testing / Deployment / Limitations / Skills / Resolution (team+mentor) /
  Safe Evidence (authenticated blob download) / Related Knowledge.
- Problem detail: "Related previously solved issues" section.
- Workspace: compact Knowledge tab reusing the same panel.
- Admin `/admin/knowledge`: status filter + Retry / Archive / Unarchive.

## 15. Real smoke results (dev, unedited)

Articles: KB-000001 library wifi, KB-000002 gate CCTV, KB-000003 hostel water.

| Query | Result |
|---|---|
| "internet keeps dropping where students study in library" (semantic) | KB-000001 @ **0.6186** |
| "security camera at college gate is offline" (semantic) | KB-000002 @ **0.7834** |
| "college bus arrives late every morning transport delay" (semantic) | **0 results** (correct) |
| "wifi" hybrid | KB-000001, sem 0.4562 / kw 0.0 / final **0.3421** (formula verified live) |
| "wifi" keyword | 0 (honest substring semantics: "wifi" ∉ "wireless") |
| "wireless" keyword | 1 |
| Case-insensitive "WIFI" keyword | matches "WiFi" titles |

Related: KB-000001 ↔ KB-000002 @ 0.2854, ↔ KB-000003 @ 0.2233 (below
threshold, shown only in related ranking, never as search hits).

## 16. E2E proof (no manual rows)

Three genuine dev problems (reporter → review → approve → assign solver1/
solver2/mentor1 → task → shareable evidence upload → solution → mentor approve
→ reporter RESOLVED → admin close) auto-published KB-000001/2/3 with real
embeddings, skills, team/mentor names, and evidence. Tickets CX-2026-003578/79/80.

## 17. Limitations

- Keyword search is substring-based (no stemming/synonyms); semantic leg
  covers meaning, hybrid is the default for that reason.
- Related ranking has no threshold by design (top-N honest scores).
- `resolution_duration_minutes` is 0 for same-minute demo closures (genuine).
- Vector search is an exact scan (fine now; index later at scale).
- Analytics explicitly out of scope.
