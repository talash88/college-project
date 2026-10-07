# Step 14 — Production-Quality UI/UX Polish + Role Experience

Polish-only pass. No backend product changes, no migrations (head stays
**012**), no AI/algorithm changes, no fake data. All visible data still comes
from real APIs.

## 1. Design direction

Restrained institutional style: slate neutrals, institutional blue primary,
green success, amber review/warning, red danger. No gradients/glows/rainbow
cards. The app already had this character; Step 14 standardized it.

## 2. Route audit (all visited in real Chrome)

Polished already, verified: login, register, dashboard (all roles), report
form + success, My Reports cards, problem detail, admin intake/duplicates,
workspace (9 tabs), notifications + bell, knowledge list/detail, analytics,
profile, 403. Fixed during audit: mobile drawer, sidebar active states,
badge inconsistencies, modal focus/escape, detail header. New: styled 404
(`not-found.tsx`).

## 3. Shared components / design system

- `src/lib/status-styles.ts` (new): one status value → one badge style
  (problem/priority/task/milestone/review/verification/duplicate/publication).
- `src/components/ui/Feedback.tsx` (new): `Badge`, `LoadingSkeleton`,
  `EmptyState`, `ErrorState` (with retry, never backend tracebacks),
  `TableShell` (scroll region with label).
- `src/lib/format.ts` (new): `formatDateTime/formatDate/formatRelative/
  formatDurationMinutes` (human-readable, never raw ISO).
- `globals.css`: added `btn-danger`; global `:focus-visible` ring for keyboard
  users; input-contrast fix preserved and re-verified in dark OS mode
  (typed text `rgb(15,23,42)` on white, `color-scheme: light`).
- Migrated to central colors: My Reports badges, admin intake status,
  DuplicatesSection (decision vs problem palettes; purple DUPLICATE removed),
  workspace task/milestone/solution states, PrioritySection levels,
  assigned/mentored worklist cards (+ location line, shared date format).

## 4. Dashboards (real data only)

- All roles: unread-notifications strip (single `unread-count` call, hidden at 0).
- Solver/mentor lists use central status badges.
- Admin: Knowledge publication state card (published/failed/archived from the
  real admin API) + shortcut cards to Knowledge Admin and Analytics.
- Kept: role stat cards, review queue, explainer, dev-only system health.

## 5. Problem detail

Summary header now shows ticket + central status badge + priority badge with
score + AI/reported category badge + location/date grid (was: blue status
only). Edit form and section order untouched; reporter-visible boundaries
unchanged.

## 6. Admin workflow

- Reject uses the new danger button; modal gained Escape-to-close and initial
  focus. Other destructive actions already confirm (withdraw/file/remove via
  `window.confirm`; archive is reversible secondary).
- State-gated actions, busy labels, and notices unchanged (already correct).

## 7. Workspace

Header, 9-tab layout, progress, files (shareable toggle kept), discussion,
solution, activity verified visually; only badge centralization changed.

## 8. Knowledge / analytics

Verified visually (list cards, filters, detail sections, related scores, admin
table, KPI cards, charts, AI Health wording). No formula or content changes.

## 9. Report form

Unchanged except the success panel gains "Report Another Problem" (resets via
reload; no forced redirect). Ticket/AI results/View Report/My Reports kept.

## 10. Responsive behavior

- Mobile drawer was broken (three disconnected menu states; sidebar always
  overlaid content). Fixed: single state in `AppLayout`, drawer with overlay,
  body scroll-lock, route-change close, large tap targets, `max-w-[85vw]`,
  keyboard-invisible when closed. Verified at 390px with screenshots.
- Tablet (768px): drawer + stacked cards verified. Desktop (1440px): full layout.
- No horizontal body overflow on any audited route; tables scroll internally.

## 11. Accessibility

Global focus-visible ring; dialogs expose `role=dialog`/`aria-modal`/labels +
Escape + autofocus; icon buttons labeled; badge text never color-only (status
text always present); form errors use `role=alert`; tables regions labeled;
disabled states visible. Sidebar active route uses `aria-current`.

## 12. Browser issues found/fixed

- Mobile drawer overlay (fixed, screenshot-verified).
- Sidebar highlighted "My Reports" on workspace pages (fixed: exact + detail-only matching).
- Duplicate React keys in workload tables (fixed with indexed keys).
- Purple DUPLICATE / always-blue statuses (centralized).
- Detail `[id]` page briefly blank from a Next-15-style `use(params)` pattern
  (fixed to Next-14 `useParams`).
- Removed dead "Teams / Soon" nav (no such route exists) and the
  "stored in PostgreSQL" profile subtitle.
- Console: no page errors across audited routes (only dev React-DevTools info
  and HMR logs). No refetch loops (parallel fetches + 30s bell poll by design).

## 13. Remaining visual limitations

- My Reports cards lack priority (API summary has no priority field; adding it
  needs a backend change — intentionally skipped).
- Date formatting is human-readable but not yet fully migrated to the shared
  lib (cosmetic; low risk to leave).
- `TableShell`/`EmptyState` components exist for future use; mass-migrating
  every list was out of scope.
- Longest AI sections still scroll (by design for demo readability).
