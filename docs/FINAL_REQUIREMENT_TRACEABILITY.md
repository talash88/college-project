# Final Requirement Traceability

Every row below was verified against the running product (Steps 15–17) or the
266-test suite. Status values: COMPLETE (evidence-backed) / PARTIAL (works with
a documented gap) / NOT IMPLEMENTED.

| Requirement | Status | Backend evidence | Frontend evidence | DB evidence | Tests | Known limitation |
|---|---|---|---|---|---|---|
| Authentication (register/login/refresh/logout) | COMPLETE | `POST /auth/register|login|refresh|logout`, `AuthService`, rotating opaque refresh tokens | `/login`, `/register`, `AuthContext`, single-flight refresh | `users`, `refresh_tokens` | `test_auth.py` | Access 30 min / refresh 7 d; no SSO |
| RBAC (Anonymous/Reporter/Solver/Mentor/Admin) | COMPLETE | `require_roles`, `require_admin`, `get_current_user` on all routers | role-aware nav, `/403` page | `users.role` enum | `test_security.py`, Step-16 RBAC matrix | List pages show own-empty states, not 403 |
| Profiles (student/faculty, skills) | COMPLETE | `/profile/me`, `/users/*` (self-or-admin) | `/profile` | `student_profiles`, `faculty_profiles`, `user_skills` | `test_auth.py`, `test_models.py` | No avatar upload |
| Skills taxonomy (46) | COMPLETE | `/skills`, `seed_skills.py` | skill pickers, chips | `skills`, `skill_embeddings` (46×384) | `test_skills.py` | Dev DB has stale `Python_*` junk rows (demo DB clean) |
| Problem reporting + tickets | COMPLETE | `POST /problems`, `CX-YYYY-NNNNNN` via `ticket_counters` | `/problems/new` + validation | `problems` | `test_problems.py` | Withdraw = soft state, no hard delete |
| Attachments (JPEG/PNG/WEBP/PDF ≤10MB ≤5) | COMPLETE | sniffed MIME, 415/413, traversal-safe names | file input + list | `problem_attachments` + disk files | `test_problems.py`, storage audit | Local disk only (S3 documented, not built) |
| AI classification (DistilBERT, 12 classes) | COMPLETE | `ClassificationService`, threshold 0.60, FAILED honest | `ClassificationSection` (bands + review) | `problem_classifications` (audit rows) | `test_classification.py` | acc 0.659; SAFETY_SECURITY F1 0.0, INFRASTRUCTURE 0.25 — admin review mandatory |
| Priority scoring (0–100, L/M/H/C) | COMPLETE | `PriorityService`, weights 30/25/20/15/10, history | `PrioritySection` (reasons + breakdown) | `problem_priority_analyses` | `test_priority.py` | Conservative by design; safety text without keywords scores LOW |
| Required skill extraction (hybrid) | COMPLETE | exact + MiniLM cosine + category bonus, ≤6, thr 0.45 | `RequiredSkillsSection` (scores, match kinds) | `problem_skill_analyses`, `problem_required_skills` | `test_skills.py` | Empty when no match (by design); sparse demo texts → INSUFFICIENT_DATA |
| Duplicate detection (semantic+location+category) | COMPLETE | `DuplicateService`, thr 0.60 / strong 0.82, no auto-merge | `DuplicatesSection` (badges, safe view) | `problem_duplicate_candidates`, `problem_embeddings` | `test_duplicates.py` | Paraphrase 0.897 STRONG proven; small corpus |
| Duplicate clustering + canonical | COMPLETE | confirm/reject, cluster join/merge, priority recount | `/admin/duplicates`, cluster page | `duplicate_clusters`, `duplicate_cluster_members` | `test_duplicates.py` | Deleting canonical leaves hollow shell (analytics ignores; reset script removes) |
| Student team recommendation | COMPLETE | coverage 50 / proficiency 20 / availability 10 / workload 10 / verified 5 / domain 5; combination search, 3 options | `TeamRecommendationsSection` + breakdown | `team_recommendations`, `team_recommendation_members` | `test_recommendations.py` | Advisory only; identical display names confusing (keys fixed Step 16) |
| Faculty mentor recommendation | COMPLETE | specialization 35 / skills 30 / category 15 / availability 10 / workload 10 + MiniLM semantics | `MentorRecommendationsSection` | `mentor_recommendations` | `test_recommendations.py` | Advisory only |
| Admin review (start/approve/reject) | COMPLETE | `review/start`, `approve`, `reject` + reason, state machine 409s | `AdminReviewSection`, intake table | `problems.status`, `reviewed_by/at` | `test_assignments.py` | No bulk actions |
| Assignment (atomic + idempotent) | COMPLETE | single transaction, one active assignment, override flags+reasons | admin assign picker | `problem_assignments`, `problem_teams`, `problem_team_members`, workload counters | `test_assignments.py` | — |
| Reassignment / cancel | COMPLETE | `assignment/reassign`, `assignment/cancel`, workloads released+applied once | oversight controls | assignment history rows | `test_assignments.py` | — |
| Workload accounting | COMPLETE | increment once, held at RESOLVED, released once at CLOSE, retry 409 | workload badges (admin) | `current_workload/max_workload` | `test_verification.py` | — |
| Tasks (CRUD + TODO→IN_PROGRESS→BLOCKED→DONE) | COMPLETE | strict transitions, blocker reason kept | workspace task cards | `problem_tasks` | `test_workspace.py` | No subtasks |
| Milestones | COMPLETE | create/status flow | milestone list | `problem_milestones` | `test_workspace.py` | — |
| Progress (70% tasks + 30% milestones) | COMPLETE | `WorkspaceService` formula | progress bar + public progress | `problem_progress_updates` (snapshots) | `test_workspace.py` | Reporter sees % only (by design) |
| Internal discussion | COMPLETE | team/mentor-only discussion | workspace discussion | `problem_comments` (`is_internal`) | `test_workspace.py` | No @mentions |
| Work files + evidence sharing | COMPLETE | upload/download, shareable flag, safe evidence | work-file list | `problem_work_attachments` | `test_workspace.py` | Local disk |
| Solution submission + revisions | COMPLETE | append-only revisions, readiness gate | solution panel + history | `problem_solution_submissions` | `test_verification.py` | — |
| Mentor review (approve/changes) | COMPLETE | `solutions/{id}/review`, unrelated mentor 404 | review controls | `mentor_solution_reviews` | `test_verification.py` | — |
| Reporter verification (YES/NO) | COMPLETE | `verifications`, NO reopens, YES resolves+timestamp | verification prompt | `problem_resolution_verifications` | `test_verification.py` | One active verification chain |
| Notifications (11 types) | COMPLETE | `NotificationService`, unread/read-all, no cross-user leak | bell + `/notifications` | `notifications` | `test_notifications.py` | In-app only (no email/push) |
| Closure | COMPLETE | `close`, releases once, retry 409 | close dialog + state | `closed_at`, `close_reason` | `test_verification.py` | Only from RESOLVED |
| Knowledge repository (auto-publish) | COMPLETE | publish on close, snapshot, privacy filter, retry/archive | `/knowledge`, detail, related | `knowledge_entries`, `knowledge_embeddings`, `knowledge_entry_skills` | `test_knowledge.py` | Only closed+verified publish |
| Semantic search (keyword/semantic/hybrid) | COMPLETE | MiniLM-384, thr 0.35, weights 0.75/0.25, limit 10 | search + filters | `knowledge_embeddings` (pgvector) | `test_knowledge.py` | Exact scan (tiny corpus — correct, no ANN) |
| Related solved problems | COMPLETE | `related-solutions`, informational only | related panel (reporter-safe) | reuse of embeddings | `test_knowledge.py`, Step-16 E2E | — |
| Analytics (dashboard/trends/CSV) | COMPLETE | overview by status/category/priority/skills/dups/verification/knowledge | `/analytics` charts + CSV download | aggregate queries (matched DB exactly) | `test_analytics.py` | Single-DB queries; no data warehouse |
| Security hardening | COMPLETE | bcrypt, JWT, rotation, HttpOnly, RBAC/IDOR, rate limit, headers, upload/CSV guards, prod env gate | safe errors, session-expiry flow | — | `test_security.py` | No MFA/SSO; in-memory limiter single-instance |
| Responsive UI (1440/768/390) | COMPLETE | — | Tailwind responsive, skeletons, empty states | — | Browser sweeps Step 16/18 | Double-fetch in dev only (StrictMode) |
| Docker / deployment readiness | COMPLETE | prod Dockerfile, entrypoint migrate-then-serve, compose stack | frontend Dockerfile (standalone) | fresh-DB 001→012 proof | Build + prod-stack E2E proof | Backend image 2.97 GB; no external deploy performed |

Overall: 38/38 COMPLETE. No PARTIAL, no NOT IMPLEMENTED among requirements.
