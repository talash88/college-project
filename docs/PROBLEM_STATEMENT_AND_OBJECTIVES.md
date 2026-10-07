# Problem Statement & Objectives

## Problem statement
Campus issues (broken infrastructure, network outages, safety hazards) are
reported through informal channels — chats, registers, word of mouth — where
they are untracked, inconsistently prioritized, assigned ad hoc, and forgotten
after fixing, so the same problems recur and nobody can measure resolution.

## Primary objective
Build a working web platform where any campus issue becomes a tracked ticket
that AI helps triage, skilled students resolve under mentorship, reporters
verify, and the institution remembers.

## Specific objectives
1. Plain-language reporting with tickets, attachments, and status tracking.
2. Local AI classification with confidence + mandatory human review.
3. Explainable 0–100 priority scoring with reasons.
4. Required-skill extraction without forced irrelevant skills.
5. Semantic duplicate detection with admin-confirmed clustering (never auto-merge).
6. Advisory team + mentor recommendations with override reasons.
7. Atomic assignment with workload safety; tasks/milestones/progress workspace.
8. Solution revisions, mentor review, reporter verification, closure.
9. In-app notifications for every state change.
10. Auto-published, privacy-filtered knowledge repository with hybrid search.
11. Honest analytics + injection-safe CSV export.
12. Hardened auth (bcrypt, JWT rotation, RBAC/IDOR, rate limits, upload guards).
13. Reproducible deployment (Docker) + curated demo environment + full docs.

## Scope
College campus deployment; single institution; English reports; in-app
notifications; local AI models; single-instance hosting.

## Out-of-scope
External LLM APIs, SSO/MFA, email/push, mobile apps, S3 integration,
multi-replica scaling, production hosting (readiness only, no live deploy).
