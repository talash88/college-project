# Demo Accounts — DEVELOPMENT / DEMO ONLY, never production

## Curated college demo (`campusxolve_demo`, password `demo_college_123`)

Built by `backend/scripts/seed_demo.py`: 10 fictional users, 8 problems in 8
lifecycle states, 2 Knowledge articles, 1 duplicate cluster.

| Login (all `@campusxolve.local`) | Name | Role | Showcases |
|---|---|---|---|
| `demo.admin` | Demo Admin | ADMIN | Intake, review, assignment, analytics |
| `demo.ananya` | Ananya Rao | REPORTER | Report → verify → knowledge |
| `demo.kabir` | Kabir Shah | REPORTER | Second reporter, duplicate member |
| `demo.rohan` / `demo.sneha` | Rohan Verma / Sneha Iyer | SOLVER | Network/portal team |
| `demo.aditya` / `demo.ishita` | Aditya Kulkarni / Ishita Bose | SOLVER | Electrical/water team |
| `demo.vikram` | Vikram Singh | SOLVER | Hardware/bus team |
| `demo.meera` | Dr. Meera Krishnan | MENTOR | Networks mentoring |
| `demo.arjun` | Prof. Arjun Nair | MENTOR | Electrical mentoring |

Password for all: `demo_college_123`. Reset: `python scripts/reset_demo.py`
(dry-run default; `--apply` deletes only `demo.*` records).

## Local dev accounts (`campusxolve` DB, from `seed_users.py`)

`admin / reporter / solver1-3 / mentor1-2 @campusxolve.local`
(passwords `dev_admin_123`, `dev_reporter_123`, `dev_solver_123`,
`dev_mentor_123`). Names: CampusXolve Admin, Test Reporter, Alex Chen,
Priya Sharma, Jordan Kim, Dr. Sarah Johnson, Prof. Michael Torres.
