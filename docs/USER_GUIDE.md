# User Guide (plain language, matches the real UI)

## Reporter (reports problems, verifies fixes)
1. **Register/Login**: `/register` (Reporter or Solver only) → `/login`.
2. **Profile**: `/profile` — bio, department, availability, your skills.
3. **Report a Problem**: `/problems/new` — title (≥5 chars), description
   (≥20 chars), location, people affected, up to 5 images/PDFs. No categories
   to pick — the AI does that.
4. **My Reports**: `/problems` — ticket, status stepper, priority.
5. **Problem detail**: AI category + confidence (low confidence honestly says
   "Needs Admin Review"), priority score with reasons, required skills,
   "Similar Reports" (suggestions only — admin decides), related solved issues,
   recommended team (safe view), comments, activity.
6. **After assignment**: safe progress %, team + mentor names (no internals).
7. **Verification**: when asked, confirm YES (resolved) or NO + reason
   (reopens the work). Bell icon + `/notifications` for every event.
8. **Knowledge Repository**: `/knowledge` — search solved problems by keyword
   or meaning; open articles for fixes that worked before.

## Solver (does the work)
1. **Assigned Problems**: `/assigned` — problems assigned to your team.
2. **Workspace**: `/problems/{id}/workspace` — tasks (create → start →
   block with reason → complete), milestones, progress updates, work files
   (evidence), internal discussion, related knowledge.
3. **Solution**: submit summary + root cause + work + testing when tasks are
   done; revisions are kept. If the mentor requests changes, revise and
   resubmit. Notifications tell you about assignments, reviews, verification.

## Mentor (guides + approves)
1. **Mentored Problems**: `/mentored` — your problems.
2. **Workspace oversight**: tasks/milestones/progress, post progress updates,
   discuss with the team.
3. **Solution review**: Approve (→ reporter verification) or Request Changes
   (+ comment). You cannot touch problems you don't mentor (404).

## Admin (runs the platform)
1. **Dashboard**: review queue (pending/awaiting assignment/in progress/
   awaiting verification), knowledge + analytics shortcuts.
2. **Intake** `/admin/problems`: filter, open a report, re-run AI, **correct
   the category**, recalculate priority, reanalyze skills/duplicates.
3. **Duplicates** `/admin/duplicates`: confirm (creates cluster + canonical
   link) or reject (never silently re-offered).
4. **Recommendations**: compare 3 team options + ranked mentors (breakdowns),
   recalculate; then **Assign** (override allowed with mandatory reason),
   reassign/cancel later with workload safety.
5. **Closure**: close RESOLVED reports → workloads release, knowledge
   auto-publishes. **Knowledge** `/admin/knowledge`: retry/archive.
   **Analytics** `/analytics`: dashboard, trends, CSV export.
