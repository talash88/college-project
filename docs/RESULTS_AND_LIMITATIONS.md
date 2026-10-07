# Results & Limitations (measured, not claimed)

## Results
- **Tests**: 266 passed; Ruff/MyPy/ESLint/tsc/build green; pip-audit clean;
  npm 17 known advisories; dev DB provably unchanged by suite.
- **AI**: DistilBERT test accuracy **0.659**, macro F1 **0.63**, weighted F1
  **0.644** (44 held-out dev samples). Live: 5/6 unseen probes correct, all
  low-confidence and honestly flagged.
- **Semantics**: true paraphrase duplicate 0.8968 (STRONG); unrelated queries
  weak; analytics counts matched DB exactly.
- **E2E**: full ticket→close→knowledge lifecycle executed twice in a real
  browser + API; workloads increment/release exactly once; 9 notification
  types delivered.
- **Security**: RBAC matrix measured; IDOR sweep clean; upload/traversal/CSV
  guards proven; prod secret validation enforced.
- **Deployment**: both Docker images built (2.97 GB / 226 MB); prod compose
  healthy; prod E2E + restart persistence proven; fresh-DB 001→012 proven.

## Limitations (acknowledged)
Small 288-sample dataset; SAFETY_SECURITY F1 0.0 and INFRASTRUCTURE 0.25;
routine low confidences (by design → human gates); MiniLM thresholds tuned on
small data; heuristic (not learned) recommenders; no ANN index (correct at
67 vectors); single-instance limiter; in-app notifications only; no SSO/MFA/
S3/mobile; backend image large; no external deployment performed.
