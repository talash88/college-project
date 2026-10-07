# Final Architecture

## High-level system architecture

```mermaid
flowchart TB
    Browser["Browser\nNext.js 14 + React 18 + TS + Tailwind"]
    FE["Frontend (port 3000)\nstandalone server"]
    API["FastAPI backend (port 8000)\nrouters → services → repositories"]
    DB[("PostgreSQL 16 + pgvector\n38 tables")]
    Disk["Local disk\nproblem-attachments"]
    HF["HF cache\nMiniLM downloads"]
    BERT["DistilBERT weights\n256 MB (mounted)"]

    Browser -->|"HTTPS, JWT Bearer + HttpOnly refresh cookie"| FE
    FE -->|"REST /api/v1 (NEXT_PUBLIC_API_URL)"| API
    API --> DB
    API --> Disk
    API --> HF
    API --> BERT
```

## Complete report lifecycle

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED: reporter POST /problems
    SUBMITTED --> UNDER_REVIEW: admin review/start
    UNDER_REVIEW --> APPROVED: admin approve
    UNDER_REVIEW --> REJECTED: admin reject + reason
    APPROVED --> ASSIGNED: admin assign (atomic, workloads +1)
    ASSIGNED --> IN_PROGRESS: first task start
    IN_PROGRESS --> AWAITING_VERIFICATION: mentor approves solution
    AWAITING_VERIFICATION --> IN_PROGRESS: reporter NOT_RESOLVED
    AWAITING_VERIFICATION --> RESOLVED: reporter RESOLVED
    RESOLVED --> CLOSED: admin close (workloads released, knowledge published)
    SUBMITTED --> DUPLICATE: admin confirms duplicate
    CLOSED --> [*]
    REJECTED --> [*]
```

## AI/ML processing pipeline (on report creation)

```mermaid
flowchart LR
    Text["title + description + location"] --> CLS["DistilBERT classifier\n12 classes, softmax"]
    CLS -->|conf < 0.60| REV["LOW_CONFIDENCE → admin review"]
    CLS --> PRI["Priority engine\nseverity 30 + affected 25 + age 20 + category 15 + dup 10"]
    Text --> SKL["Skill extractor\nexact phrases + MiniLM cosine (384-d, pgvector) + category bonus"]
    Text --> EMB["MiniLM problem embedding → pgvector"]
    EMB --> DUP["Duplicate search\n0.85 semantic + 0.10 location + 0.05 category\ncandidate ≥ 0.60, STRONG ≥ 0.82"]
    SKL --> REC["Team + mentor recommenders\n(admin advisory only)"]
    DUP --> ADMIN["Admin confirms → cluster + canonical"]
```

## Role interaction

```mermaid
flowchart TB
    R["REPORTER\nreports, comments, verifies"]
    S["SOLVER\ntasks, files, solutions"]
    M["MENTOR\nmilestones, reviews"]
    A["ADMIN\nreviews, assigns, closes"]
    P["Problem + workspace"]

    R -->|"creates"| P
    A -->|"assigns team + mentor"| P
    S -->|"works"| P
    M -->|"guides + approves"| P
    R -->|"verifies"| P
    A -->|"closes → knowledge"| P
```

## Deployment architecture

```mermaid
flowchart TB
    Net["Same parent domain (recommended)"]
    FEc["frontend container\nnode server.js :3000"]
    BEc["backend container\nwait → alembic → uvicorn :8000"]
    PG[("postgres container\npgvector/pgvector:pg16 + pgdata")]
    UP[("backend-uploads")]
    HC[("backend-hfcache")]
    W["ml/artifacts (ro mount)"]

    Net --> FEc
    FEc --> BEc
    BEc --> PG
    BEc --> UP
    BEc --> HC
    BEc --> W
```

## Data flow (browser → API → DB → AI)

1. Browser (axios + in-memory access token, HttpOnly refresh cookie) calls
   `NEXT_PUBLIC_API_URL/api/v1/...`.
2. Middleware: request ID → security headers → in-memory rate limit → CORS → JWT auth → RBAC guard.
3. Service layer runs business rules + AI (classifier/priority/skills/
   embeddings/recommenders), appending audit rows rather than overwriting.
4. Repositories persist via SQLAlchemy 2.0 async to Postgres; vectors via pgvector.
5. Responses are role-filtered (reporter-safe views strip IDs/internals).

## Layers

- **Frontend**: Next.js 14 App Router, React 18, TypeScript (strict), Tailwind,
  axios client with single-flight token refresh. 22 routes.
- **Backend**: FastAPI, Pydantic v2 (+ settings with prod fail-fast),
  SQLAlchemy 2.0 async, Alembic (001→012). Layering: `api` → `services` →
  `repositories` → `models`. 94 routes.
- **Database**: PostgreSQL 16 + pgvector extension (migration 002); 38 tables;
  UUID PKs; `ticket_counters` for `CX-YYYY-NNNNNN`.
- **AI/ML**: DistilBERT fine-tune (local), all-MiniLM-L6-v2 sentence embeddings
  (384-d), deterministic priority weights, heuristic recommenders — all behind
  human-in-the-loop gates.
- **Storage**: local-disk adapter (`storage/problem-attachments`), swappable.
- **Auth**: bcrypt `$2b$`, JWT access (30 min) + rotating opaque refresh
  (HttpOnly cookie, 7 d), RBAC roles, 404-masked IDOR.
- **Notifications**: in-app, typed, read-state tracked.
- **Docker**: prod images + compose with health-gated startup (see
  `docs/STEP_17_DEPLOYMENT.md`).
