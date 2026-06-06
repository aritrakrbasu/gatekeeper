# Frontend Step 0 — Shared UI Primitives Migration

This document records the extraction of reusable UI primitives from existing Gatekeeper frontend code. No Copilot feature code was added in this step.

## New Files

| File | Purpose |
|------|---------|
| `frontend/gatekeeper/src/components/shared/GlassOverlay.jsx` | Centered glassmorphism modal shell |
| `frontend/gatekeeper/src/components/shared/GlassDrawer.jsx` | Right-side drawer shell (480px desktop, full-screen mobile) |
| `frontend/gatekeeper/src/components/shared/TerminalMarkdown.jsx` | Dark terminal-style ReactMarkdown renderer |
| `frontend/gatekeeper/src/components/shared/ActivityLog.jsx` | Generic timestamped activity log panel |
| `frontend/gatekeeper/src/components/shared/index.js` | Barrel exports |

## Source Extractions

### GlassOverlay

**From:** `RepoDetails.jsx` (MR details, credential, branch credential modals) and `ConnectRepositoryModal.jsx`

Two variants preserve existing behavior:

- **`split`** (default) — RepoDetails pattern: separate backdrop layer with `onClick` close, `z-[100]`, glass panel (`bg-white/95 backdrop-blur-2xl`)
- **`unified`** — ConnectRepositoryModal pattern: backdrop on root element, `z-50`, opaque white panel

### GlassDrawer

**New shell** for Copilot Step 3. Not wired into any page yet.

- Desktop: `md:w-[480px]`
- Mobile: `w-full` (full-screen sheet)
- Tailwind only; same backdrop pattern as `GlassOverlay` split variant

### TerminalMarkdown

**From:** `RepoDetails.jsx` AI summary block (~L1244–1341)

- Exports `terminalMarkdownComponents` for the full ReactMarkdown component map
- Preserves prose classes and link/code/table styling
- Security: relies on ReactMarkdown default behavior (no raw HTML rendering)

### ActivityLog

**From:** `RepoDetails.jsx` `ProgressLogsViewer` rendering (~L2057–2101)

- Presentational component; accepts `logs`, `isLoading`, `isLive`, `title`
- `ProgressLogsViewer` in RepoDetails remains as a thin data-fetching wrapper over `ActivityLog`

## Consumer Updates

| File | Change |
|------|--------|
| `pages/RepoDetails.jsx` | Three modals → `GlassOverlay`; AI summary → `TerminalMarkdown`; `ProgressLogsViewer` → `ActivityLog` |
| `components/ConnectRepositoryModal.jsx` | Root overlay → `GlassOverlay` unified variant |

## Import Pattern

```jsx
import {
  GlassOverlay,
  GlassDrawer,
  TerminalMarkdown,
  ActivityLog,
} from "../components/shared";
```

## Tests

Vitest + Testing Library added under `frontend/gatekeeper`:

```bash
cd frontend/gatekeeper
npm test
```

Test files:

- `src/components/shared/GlassOverlay.test.jsx`
- `src/components/shared/GlassDrawer.test.jsx`
- `src/components/shared/TerminalMarkdown.test.jsx`
- `src/components/shared/ActivityLog.test.jsx`

## Next Step (Step 1)

Do **not** import Copilot APIs yet. Step 1 adds:

- `copilotApi.js` / `copilotStream.js`
- `queryKeys.copilot`
- Thin React Query hooks

`GlassDrawer` and `ActivityLog` will be consumed in Step 3 (Copilot drawer and activity panel).

## Verification Checklist

- [ ] MR details modal opens/closes identically (backdrop click + close button)
- [ ] Credential modals unchanged
- [ ] Connect Repository modal unchanged
- [ ] AI summary markdown styling unchanged
- [ ] Progress logs poll and display identically during review
- [ ] `npm test` passes in `frontend/gatekeeper`
