# Demo Script (10–15 minutes, live, nothing faked)

Setup first: `docs/FINAL_DEMO_CHECKLIST.md`. Use the curated demo DB
(`demo.*` accounts, password `demo_college_123`).

| Min | Say | Click |
|---|---|---|
| 0–1 | "CampusXolve AI turns campus complaints into tracked, AI-assisted teamwork." | Show `/login`. |
| 1–3 | "A student reports in plain words — no forms expertise needed." Login as `demo.ananya`. | Report a WiFi issue at `/problems/new`; submit; read the ticket aloud. |
| 3–5 | "The AI classifies, scores priority with reasons, and extracts skills — and admits uncertainty." | Problem detail: category + confidence, priority reasons, skill chips. |
| 5–6 | "It also finds possible duplicates — but never merges alone." | Similar Reports panel (badges, admin-only note). |
| 6–8 | "Admin reviews everything." Logout, login `demo.admin`. | Intake → classification correction control, recommendations with breakdowns → Assign team+mentor. |
| 8–10 | "The team works in a private workspace." Login `demo.rohan`. | `/assigned` → workspace: create+start a task, milestone, progress bar moves. |
| 10–11 | "Solutions go through mentor review with revisions." | Submit solution (or show existing rev history on CX-…-000008). |
| 11–12 | "The reporter has the last word." Login `demo.ananya`. | Verification prompt on the AWAITING_VERIFICATION problem. |
| 12–13 | "Solved problems become searchable knowledge." | `/knowledge`: semantic query "wifi keeps dropping" → article. |
| 13–14 | "Management sees the whole picture." Login `demo.admin`. | `/analytics`: status counts, categories, skill demand, CSV. |
| 14–15 | Close: "AI assists, humans decide — every step is explainable and audited." | Thank the evaluators; offer the docs index. |

If anything breaks: `docs/DEMO_FALLBACK_PLAN.md` — never fake a result; show
the honest error state and recover.
