# Testing & Validation

- **Suite**: 266 pytest tests (`tests/`: auth, problems, classification,
  priority, skills, duplicates, recommendations, assignments, workspace,
  verification, notifications, knowledge, analytics, security, models,
  foundation). Unit + integration + workflow E2E (full lifecycle scripts in
  `scripts/smoke_*.py` style coverage inside tests).
- **Isolation**: per-process recreated `campusxolve_test` DB (drop → migrate →
  seed); suite fails fast if it ever points at dev. Proven: dev counts
  19/6/3/0/36 identical before/after.
- **RBAC/IDOR**: role-matrix tests + measured live matrix (401/403/404);
  cross-user reads/patches → 404; anon → 401.
- **AI tests**: classifier threshold/FAILED paths (missing-artifact monkeypatch),
  priority components, skill relevance, duplicate paraphrase/negative cases,
  recommendation eligibility.
- **Concurrency**: idempotent assignment/retry-close tests (409, no double
  workload change).
- **Storage**: MIME/oversize/traversal tests + `audit_storage.py` (0 missing).
- **Browser**: Browser Control journeys (4 roles, 1440/768/390, 25+ routes,
  zero console errors), validation/empty/offline checks. No Selenium/Cypress.
- **Audits**: `pip-audit` clean; npm 17 known advisories (Next.js/PostCSS/
  minimatch — documented, no new); prod-stack E2E + persistence proof.
- **Gates**: pytest -v, ruff, mypy (strict, 120 files), alembic head, ESLint,
  tsc, next build — all green at Steps 16/17/18 baselines.
