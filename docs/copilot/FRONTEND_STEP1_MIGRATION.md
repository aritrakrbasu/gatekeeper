# Frontend Step 1 — Copilot API & React Query Foundation

Step 1 adds the Copilot data layer only. No UI components, session hooks, or drawer integration.

## New module: `features/copilot/`

```
frontend/gatekeeper/src/features/copilot/
├── api/
│   ├── copilotApi.js       # REST client
│   ├── copilotStream.js    # SSE streaming (fetch + ReadableStream)
│   └── index.js
├── hooks/
│   ├── useCopilotBootstrap.js
│   ├── useCopilotState.js
│   ├── useCopilotConversations.js
│   ├── useCreateCopilotConversation.js
│   ├── usePendingApprovals.js
│   ├── hooks.test.jsx
│   └── index.js
├── utils/
│   ├── parseSSE.js
│   ├── parseSSE.test.js
│   └── index.js
└── index.js
```

## Shared infrastructure changes

| File | Change |
|------|--------|
| [`services/api.js`](frontend/gatekeeper/src/services/api.js) | Exported `apiRequest` and `API_BASE_URL` for reuse |
| [`services/queryClient.js`](frontend/gatekeeper/src/services/queryClient.js) | Added `queryKeys.copilot` factory |

## REST API (`copilotApi.js`)

| Method | Endpoint |
|--------|----------|
| `createConversation` | `POST /api/copilot/conversations` |
| `getBootstrap` | `GET /api/copilot/conversations/{id}/bootstrap` |
| `getState` | `GET /api/copilot/conversations/{id}/state` |
| `getExecution` | `GET /api/copilot/conversations/{id}/execution` |
| `getConversations` | `GET /api/copilot/conversations` |
| `getPendingApprovals` | `GET /api/copilot/approvals/pending` |

Uses `apiRequest` — same JWT auth and 401 redirect as the rest of the app.

## SSE (`copilotStream.js`)

Separate from `api.js` because SSE requires `fetch` + stream parsing, not JSON `response.json()`.

| Function | Endpoint | Method |
|----------|----------|--------|
| `streamAsk` | `/conversations/{id}/ask` | POST |
| `streamResume` | `/conversations/{id}/resume` | POST |
| `reconnectStream` | `/conversations/{id}/stream` | GET |

All stream functions:

- Send `Authorization: Bearer <token>` from `localStorage`
- Support `Last-Event-ID` header for resume
- `reconnectStream` also supports `last_event_id` and `thread_id` query params
- Return `{ abort() }` handle for cleanup

## Query keys

```javascript
queryKeys.copilot.bootstrap(conversationId)
queryKeys.copilot.state(conversationId)
queryKeys.copilot.conversations(filters)
queryKeys.copilot.execution(conversationId)
queryKeys.copilot.pendingApprovals(repositoryId)
```

## Import pattern

```javascript
import {
  copilotApi,
  streamAsk,
  useCopilotBootstrap,
  useCreateCopilotConversation,
} from "../features/copilot";
```

## Tests

```bash
cd frontend/gatekeeper
npm test
```

New test files:

- `features/copilot/utils/parseSSE.test.js`
- `features/copilot/api/copilotApi.test.js`
- `features/copilot/api/copilotStream.test.js`
- `features/copilot/hooks/hooks.test.jsx`

## Next step (Step 2)

Add session orchestration — **not** in this step:

- `useCopilotSSE.js` — wraps `streamAsk` / `streamResume` / `reconnectStream`
- `useCopilotSession.js` — create → bootstrap → message dispatch
- `constants/streamEvents.js`

## Verification checklist

- [ ] `npm test` passes
- [ ] `npm run build` passes
- [ ] No Copilot UI rendered
- [ ] `createConversation({ repository_id, mr_iid })` callable from devtools mutation test
