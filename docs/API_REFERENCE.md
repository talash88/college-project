# API Reference (94 routes, derived from the live OpenAPI schema)

Base: `{NEXT_PUBLIC_API_URL}/api/v1`. Auth: Bearer access JWT; refresh via
HttpOnly cookie. Roles: ANON / REPORTER / SOLVER / MENTOR / ADMIN.
Cross-user objects return 404 (existence hidden); state violations return
409/422.

## Auth — open except `me`
| Method | Route | Access | Purpose |
|---|---|---|---|
| POST | `/auth/register` | ANON (REPORTER/SOLVER only; ADMIN/MENTOR 403) | Create account |
| POST | `/auth/login` | ANON | Access token + set refresh cookie |
| POST | `/auth/refresh` | refresh cookie | Rotate session, new access token |
| POST | `/auth/logout` | cookie | Revoke session, clear cookie |
| GET | `/auth/me` | any user | Current user |

## Profile / users / skills
| Method | Route | Access | Purpose |
|---|---|---|---|
| GET/PATCH | `/profile/me` | self | View / edit own profile |
| GET/POST | `/profile/me/skills` | self | List / add own skills |
| PATCH/DELETE | `/profile/me/skills/{id}` | self | Edit / remove own skill |
| GET | `/skills`, `/skills/{id}` | user | Taxonomy |
| GET | `/users`, `/users/{id}` (+ `/student-profile`, `/faculty-profile`, `/skills`) | ADMIN or self | Directory (admin) / own records |

## Problems
| Method | Route | Access | Purpose |
|---|---|---|---|
| POST | `/problems` | REPORTER+ (any role) | Submit report → runs AI pipeline |
| GET | `/problems/me`, `/problems/me/stats` | owner | Own reports + counts |
| GET | `/problems/assigned/me`, `/problems/mentored/me` | SOLVER / MENTOR | Worklists |
| GET | `/problems/{id}` | visible users | Role-filtered detail |
| PATCH/DELETE | `/problems/{id}` | owner (open states) | Edit / withdraw |
| GET | `/problems/{id}/activity` | visible | Audit trail |
| GET/POST | `/problems/{id}/comments` | visible (admin notes internal) | Comments |
| GET | `/problems/{id}/attachments` | visible | List files |
| POST | `/problems/{id}/attachments` | owner (open states) | Upload (multipart) |
| DELETE | `/problems/{id}/attachments/{aid}` | owner/admin | Remove file |

## AI read views (role-filtered; admin sees more)
`GET /problems/{id}/classification`, `/classifications` (history),
`/priority`, `/required-skills`, `/duplicates`, `/team-recommendations`
(+`/history`), `/mentor-recommendations` (+`/history`), `/related-solutions`.

## Admin workflow (ADMIN only)
`GET /admin/problems` (filters) · `GET /admin/problems/eligible-solvers` ·
`GET /admin/problems/{id}` · `POST …/review/start|approve|reject` ·
`POST …/classification/run|review` · `POST …/priority/recalculate` ·
`POST …/skills/reanalyze` · `POST …/duplicates/reanalyze` ·
`POST …/recommendations/team|mentor/recalculate` ·
`POST …/assign` · `GET …/assignment` ·
`POST …/assignment/reassign|cancel` · `POST …/close`.
Duplicates: `POST /admin/duplicate-candidates/{cid}/confirm|reject`;
`GET /admin/duplicate-clusters[/{id}]`.

## Workspace (team/mentor of the assignment; reporter 403)
Tasks: `GET/POST /problems/{id}/tasks`, `PATCH/DELETE …/tasks/{tid}` ·
Milestones: `GET/POST …/milestones`, `PATCH …/milestones/{mid}` ·
`GET/POST …/progress-updates` · `GET …/workspace` (overview + progress %) ·
Discussion: `GET/POST …/discussion` · Work files: `GET/POST …/work-files`,
`GET …/work-files/{fid}/download`, `PATCH …/shareable`, `DELETE …` ·
`GET …/public-progress` (reporter-safe %).

## Solutions / verification
`GET …/solution/readiness` · `GET/POST …/solutions` · `GET …/solutions/latest`
· `POST …/solutions/{sid}/review` (mentor: APPROVED/CHANGES_REQUESTED) ·
`GET/POST …/verifications` (reporter: RESOLVED/NOT_RESOLVED) ·
`GET …/solution/safe` + `GET …/solution/evidence/{fid}/download` (safe view).

## Notifications / knowledge / analytics / health
`GET /notifications?unread_only&limit` · `GET …/unread-count` ·
`PATCH …/{nid}/read` · `POST …/read-all`.
`GET /knowledge?query&mode&category…` · `GET /knowledge/{ref}` ·
`GET …/related` · `GET …/evidence/{fid}/download` ·
Admin: `GET /admin/knowledge`, `POST …/{eid}/retry`, `PATCH …/archive|unarchive`.
Admin: `GET /admin/analytics/dashboard|trends`,
`GET …/export/problems.csv|skills.csv`.
`GET /` (API info) · `GET /health` (status/db/pgvector/environment).
