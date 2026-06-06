# Frontend Step 3 — Copilot UI & RepoDetails Integration

First visible Copilot experience: launcher in MR modal, right-side drawer, session-backed workspace.

## New structure

```
features/copilot/
├── containers/
│   ├── CopilotLauncher.jsx    # MR modal entry + preflight
│   ├── CopilotDrawer.jsx      # GlassDrawer shell (z-110)
│   └── CopilotWorkspace.jsx   # Layout composer (useCopilotSession)
├── panels/
│   ├── CopilotChatPanel.jsx
│   ├── InvestigationPlanPanel.jsx
│   ├── ApprovalCard.jsx
│   └── CopilotActivityStrip.jsx
├── chat/
│   ├── MessageList.jsx
│   ├── UserMessage.jsx
│   ├── AssistantMessage.jsx   # TerminalMarkdown
│   ├── StreamingIndicator.jsx
│   └── QuestionInput.jsx      # Enter / Shift+Enter
└── utils/
    ├── copilotStatus.js
    ├── planStepStatus.js
    └── activityEvents.js
```

## RepoDetails integration (~40 lines)

| Addition | Purpose |
|----------|---------|
| `copilotOpen`, `copilotMr` | Local drawer state |
| `openCopilotDrawer` / `closeCopilotDrawer` | Open/close handlers |
| `<CopilotLauncher />` | Inside MR modal (before AI summary) |
| `<CopilotDrawer />` | Page-level mount when `copilotMr` set |

Mobile: opening Copilot closes the MR modal (`max-width: 767px`).

No Copilot business logic in RepoDetails — only state + mount points.

## User flow

1. Open MR modal → launcher preflights `GET .../mrs/{iid}/execution`
2. Click **Investigate with Copilot** → drawer opens, session resolves/creates conversation
3. Bootstrap hydrates plan + messages
4. User asks via `QuestionInput` → streamed assistant response in `TerminalMarkdown`
5. Plan steps update via bootstrap refetch; activity strip shows node events
6. `approval_required` → `ApprovalCard` blocks input until approve/reject/modify
7. Close drawer → `enabled: false` cleans up SSE; reopen resumes via session

## API addition

`copilotApi.getMrExecution(repositoryId, mrIid)` — MR preflight for launcher.

## Not included (Step 4+)

- `/repositories/:id/copilot` route
- KnowledgeSourcesPanel
- ReasoningPathPanel
- Conversation history page

## Tests

```bash
cd frontend/gatekeeper
npm test
```

New tests:

- `chat/QuestionInput.test.jsx`
- `panels/ApprovalCard.test.jsx`
- `containers/CopilotLauncher.test.jsx`
- `containers/CopilotWorkspace.test.jsx`
- `utils/planStepStatus.test.js`
- `utils/activityEvents.test.js`

## Verification checklist

- [ ] Launcher shows loading / unavailable / ready states
- [ ] Drawer opens at 480px desktop, full-screen mobile
- [ ] Ask question streams response
- [ ] Investigation plan renders step states
- [ ] Approval card calls `session.resume()`
- [ ] Close and reopen drawer without errors
- [ ] `npm test` and `npm run build` pass
