# Frontend Step 2 — Session Runtime Migration

Step 2 adds Copilot session orchestration hooks. No UI components, no RepoDetails integration.

## New files

| File | Purpose |
|------|---------|
| `features/copilot/constants/streamEvents.js` | SSE event + connection status constants |
| `features/copilot/utils/applyStreamEvent.js` | Pure stream event reducer + bootstrap helpers |
| `features/copilot/hooks/useCopilotSSE.js` | SSE lifecycle, reconnect, `lastEventId` tracking |
| `features/copilot/hooks/useCopilotSession.js` | Conversation resolution, bootstrap hydration, transcript state |

## `useCopilotSSE`

Manages one SSE connection per mounted conversation.

| Export | Description |
|--------|-------------|
| `connectAsk(body)` | Start ask stream (`POST .../ask`) |
| `connectResume(body)` | Start resume stream (`POST .../resume`) |
| `reconnect()` | Reconnect-only stream (`GET .../stream`) |
| `disconnect()` | Abort active stream |
| `connectionStatus` | `idle` \| `connecting` \| `connected` \| `disconnected` \| `error` |
| `lastEventId` | Latest numeric SSE `id` for resume |

Cleanup triggers:

- Component unmount
- `conversationId` change (resets `lastEventId`)
- `enabled: false` (drawer close — wired in Step 3)

## `useCopilotSession`

### Inputs

```javascript
useCopilotSession({
  repositoryId,
  mrIid,              // optional — used to create/find conversation
  conversationId,     // optional — skip resolution when provided
  enabled: true,      // false when drawer closed
});
```

### Conversation resolution

1. If `conversationId` provided → use directly
2. Else list conversations for `repositoryId`
3. Resume newest `running` / `waiting_approval` conversation if found
4. Else `createConversation({ repository_id, mr_iid })`

### State ownership

| Field | Store |
|-------|-------|
| `conversationId`, bootstrap snapshot fields | React Query bootstrap + local mirror |
| `messages`, `activityEvents`, stream flags | Local hook state |
| `lastEventId`, `connectionStatus` | `useCopilotSSE` |

### Actions

| Action | Behavior |
|--------|----------|
| `ask(question)` | Append user + streaming assistant messages, `connectAsk` |
| `resume(decision, modifiedArgs?)` | `connectResume`, clear awaiting approval |
| `clearError()` | Reset error banner state |
| `reconnect()` | Delegate to SSE hook (survives mid-stream disconnect) |

### Event routing (`applyStreamEvent`)

| Event | Effect |
|-------|--------|
| `response_chunk` | Append to streaming assistant message |
| `node_started` / `node_completed` | Append to `activityEvents` |
| `approval_required` | Set `pendingApproval`, `isAwaitingApproval` |
| `interrupted` | Set `isAwaitingApproval` |
| `plan_step_completed` | Refetch bootstrap |
| `knowledge_proposed` | Update manifest + activity log |
| `done` | Finalize message, refetch bootstrap, `isStreaming = false` |
| `error` | Set `error`, stop streaming |

## Import pattern

```javascript
import { useCopilotSession, STREAM_EVENTS } from "../features/copilot";
```

## Tests

```bash
cd frontend/gatekeeper
npm test
```

New tests:

- `utils/applyStreamEvent.test.js` — event routing coverage
- `hooks/useCopilotSSE.test.jsx` — lifecycle + `lastEventId`
- `hooks/useCopilotSession.test.jsx` — resolution, ask, approval, done refresh

## Next step (Step 3)

Wire session into UI:

- `CopilotWorkspace` consumes `useCopilotSession`
- `CopilotDrawer` passes `enabled` for drawer-close cleanup
- `RepoDetails` launcher opens drawer with `repositoryId` + `mrIid`

## Verification checklist

- [ ] `npm test` passes
- [ ] `npm run build` passes
- [ ] No Copilot UI rendered
- [ ] `done` event triggers bootstrap refetch
- [ ] `approval_required` populates `pendingApproval`
