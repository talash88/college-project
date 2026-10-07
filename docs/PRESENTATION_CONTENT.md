# Presentation Content (slide-ready, 15 slides)

1. **Title** — CampusXolve AI: AI-assisted campus problem resolution. Team,
   college, year.
2. **Problem** — Complaints lost in chats; no tracking, no priority, no memory.
3. **Proposed solution** — Ticketed reports → AI triage → skilled teams →
   verified closure → searchable knowledge. Humans decide, AI assists.
4. **Objectives** — Report in plain words; explainable AI triage; right team;
   verified fix; institutional memory.
5. **Architecture** — Next.js → FastAPI → Postgres+pgvector → local AI.
   (Use FINAL_ARCHITECTURE diagram A.)
6. **Modules** — Auth, reporting, AI engine, recommendations, workspace,
   knowledge, analytics. (TEAM_MODULES for owners.)
7. **AI/ML** — DistilBERT (12 classes, acc 0.659 dev), MiniLM embeddings,
   explainable priority, semantic duplicates. Emphasize human-in-the-loop.
8. **Workflow** — Lifecycle diagram B; walk one ticket end to end.
9. **Database** — 38 tables, UUIDs, audit histories, vectors; 001→012.
10. **Security** — bcrypt, JWT rotation, RBAC/IDOR, rate limits, upload guards.
11. **Testing** — 266 tests, isolated DB, RBAC/IDOR suites, browser journeys,
    audits. Dev DB provably untouched.
12. **Results** — E2E proven (ticket→close→KB), 0.897 paraphrase match,
    analytics = DB exactly, Docker prod proof.
13. **Limitations** — 288-sample data, 2 weak classes, single instance, no
    external deploy.
14. **Future scope** — Real data, calibration, SSO, S3, ANN index, mobile.
15. **Conclusion** — Working, honest, deployable system ready for campus use.
