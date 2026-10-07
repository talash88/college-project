# Security Overview (as implemented, Step 15 + Step-17 bcrypt fix)

| Control | Implementation |
|---|---|
| Password hashing | bcrypt `$2b$` directly (passlib removed — it 500'd on fresh installs) |
| Tokens | JWT access 30 min (memory only) + rotating opaque refresh, hashed server-side |
| Cookies | HttpOnly, `Secure` in prod, `SameSite=Lax`, path-scoped; reuse/revocation tested |
| RBAC | `require_roles`/`require_admin` on all 94 routes; measured matrix |
| IDOR | Ownership/team/mentor checks; invisible objects 404 (never 403-leak) |
| Rate limiting | In-memory sliding window (auth 20, upload 30, AI 60, search 120, default 600/min); off in tests |
| CORS | Explicit origins; `*` refused in prod; methods/headers allowlisted in prod |
| Headers | Security-headers middleware + per-request ID (`X-Request-ID`), safe 500 envelope |
| Uploads | MIME sniffing, 10 MB/5-file caps, traversal-safe names, shareability flags |
| CSV export | `=+-@` prefix injection neutralized; no sensitive fields; admin-only |
| Prod boot | Refuses default/short JWT secret, bad FRONTEND_URL, wildcard CORS |
| Errors | No tracebacks/secrets to clients; logs carry request IDs |

Limitations: no MFA/SSO; single-instance limiter (no Redis); in-app
notifications only; dev/demo passwords documented (never production); npm 17
known advisories (framework-level, documented).
