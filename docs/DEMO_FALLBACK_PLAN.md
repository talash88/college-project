# Demo Fallback Plan (recover — never fake)

| Failure | Recovery |
|---|---|
| No internet | Everything except first-time model download works offline. Pre-boot once with internet; HF cache + weights persist. Say so explicitly. |
| Docker not running (macOS) | `colima start`, then `docker compose -f docker-compose.prod.yml up -d`. |
| Model download unavailable | App boots; classification shows honest `FAILED`. Report still saves — DEMONSTRATE that instead of hiding it. |
| Backend not started | `cd backend && python3 -m uvicorn app.main:app --reload`; check `/api/v1/health`. |
| Frontend port busy | `lsof -ti:3000 \| xargs kill`, restart `npm run dev` (inside `frontend/`). |
| Browser session expired | Login again (30-min access token); refresh cookie lasts 7 days. Keep a tab on `/login` ready. |
| AI low confidence | Expected behavior — point at "Needs Admin Review" and correct it as admin. Never claim high accuracy. |
| Wrong DB / empty demo | Verify DB name (`campusxolve_demo`), re-run `seed_demo.py`; check health `environment` field. |
| Port/db conflicts | One stack at a time: dev (8000/3000) OR prod compose — never both. |

Golden rule: if a feature errors live, read the honest error aloud, recover
with the command above, and continue. Evaluators reward honesty over theatre.
