# Final Demo Checklist (presentation day)

## Before leaving home
- [ ] Laptop charged + charger; phone hotspot as backup internet.
- [ ] Repo opens; `docs/DEMO_SCRIPT.md` + `docs/DEMO_FALLBACK_PLAN.md` bookmarked.
- [ ] Demo credentials written down (`demo.*`, `demo_college_123`).

## Before presentation (15 min early)
- [ ] `colima start` (macOS); `docker start campusxolve-postgres` if dev route.
- [ ] Dev route: backend `:8000/health` healthy + frontend `:3000/login` 200.
      OR prod route: `docker compose -f docker-compose.prod.yml up -d`.
- [ ] Demo DB present (`campusxolve_demo`, 8 problems) — or `seed_demo.py` ready.
- [ ] Browser tabs open: login, dashboard, one problem, workspace, knowledge,
      analytics. Logged out to start clean (or logged in as reporter).
- [ ] Console closed, zoom 100%, 1440px if projector allows.

## During
- [ ] Follow `DEMO_SCRIPT.md` order; read tickets/AI outputs aloud.
- [ ] If anything fails: fallback plan — recover, never fake.

## After
- [ ] Log out demo accounts; stop stack (`down` for prod compose).
- [ ] Note any evaluator question you couldn't answer for the report.
