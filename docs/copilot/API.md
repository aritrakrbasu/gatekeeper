# Copilot Frontend API

JWT-protected endpoints under `/api/copilot`. All conversation resources are scoped to the authenticated user and repository access rules.

## MR execution resolution

The frontend can start Copilot with only `repository_id` and `mr_iid`. The backend resolves the graph-backed ARIL review execution internally.

### Optional preflight

`GET /api/repositories/{repository_id}/mrs/{mr_iid}/execution`

JWT required. Repository access required.

Response:

```json
{
  "repository_id": "82576405",
  "mr_iid": 42,
  "subject_id": "mr:42:82576405",
  "execution_id": "529525c3-7ae8-40d6-89bd-d72ad2a5d4bf",
  "graph_id": "graph-38ef6d1d20461f06",
  "status": "graph_built",
  "copilot_ready": true
}
```

Errors:

| Status | Detail | Meaning |
|--------|--------|---------|
| 403 | Access denied for repository ... | User not connected to repository |
| 404 | `no_captured_review` | No ARIL execution with decision graph for this MR |

Resolution flow (server-side only):

```
repository_id + mr_iid
  → subject_id = mr:{mr_iid}:{repository_id}
  → peil_subjects.latest_execution_id (with graph fallback)
  → graph-backed execution
```

### Create conversation with MR

`POST /api/copilot/conversations`

Supply **exactly one** of `execution_id` or `mr_iid`:

```json
{
  "repository_id": "82576405",
  "mr_iid": 42
}
```

When `mr_iid` is provided, the server resolves `execution_id` before creating the checkpoint. No frontend subject-id or ARIL knowledge required.

## Conversation listing

`GET /api/copilot/conversations`

Query parameters:

| Parameter | Description |
|-----------|-------------|
| `repository_id` | Filter by repository |
| `execution_id` | Filter by linked ARIL execution |
| `status` | `running`, `waiting_approval`, `completed`, or `failed` |
| `page` | Page number (default `1`) |
| `page_size` | Page size (default `20`, max `100`) |

Response:

```json
{
  "items": [
    {
      "conversation_id": "conv-...",
      "execution_id": "exec-...",
      "repository_id": "82576405",
      "status": "completed",
      "last_question": "Why was this rejected?",
      "last_updated": "2026-06-06T12:00:00Z",
      "pending_approval": false
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## Conversation state

`GET /api/copilot/conversations/{conversation_id}/state`

Derived from LangGraph checkpoint state and `copilot_conversation_checkpoints`. Survives process restarts.

Response:

```json
{
  "conversation_id": "conv-...",
  "thread_id": "conv-...",
  "status": "waiting_approval",
  "execution_id": "exec-...",
  "copilot_execution_id": "exec-copilot-...",
  "current_node": "approval_gate",
  "current_plan": {
    "plan_id": "plan-...",
    "profile": "outcome_explanation",
    "steps": [],
    "step_cursor": 1
  },
  "pending_approval": {
    "reason": "...",
    "tool_name": "post_gitlab_mr_comment",
    "tool_args": {},
    "risk_level": "mutating",
    "estimated_scope": "1 comment",
    "step_id": "s1",
    "requires_admin": false
  },
  "checkpoint_id": "1f2e...",
  "checkpoint_version": 3,
  "last_updated": "2026-06-06T12:00:00Z"
}
```

## Execution navigation link

`GET /api/copilot/conversations/{conversation_id}/execution`

Links conversation UI to Replay, Graph Explorer, and Execution Explorer.

```json
{
  "conversation_id": "conv-...",
  "execution_id": "exec-...",
  "copilot_execution_id": "exec-copilot-...",
  "graph_id": "graph-...",
  "subject_id": "subject-...",
  "repository_id": "82576405"
}
```

## Bootstrap hydration

`GET /api/copilot/conversations/{conversation_id}/bootstrap`

Single-request screen hydration.

```json
{
  "conversation": { "...": "ConversationCheckpointResponse" },
  "state": { "...": "ConversationStateResponse" },
  "execution": {
    "execution_id": "exec-...",
    "copilot_execution_id": "exec-copilot-...",
    "graph_id": "graph-...",
    "subject_id": "subject-...",
    "repository_id": "82576405",
    "status": "graph_built"
  },
  "knowledge_manifest": {},
  "current_plan": {},
  "pending_approval": null,
  "checkpoint": {
    "checkpoint_id": "1f2e...",
    "checkpoint_version": 3,
    "thread_id": "conv-...",
    "last_updated": "2026-06-06T12:00:00Z"
  }
}
```

## Pending approval queue

`GET /api/copilot/approvals/pending`

Query parameters: `repository_id`, `page`, `page_size`.

Backed by `copilot_approvals` with `status=pending`.

```json
{
  "items": [
    {
      "approval_id": "appr-...",
      "conversation_id": "conv-...",
      "repository_id": "82576405",
      "tool_name": "post_gitlab_mr_comment",
      "risk_level": "mutating",
      "reason": "Post review comment",
      "created_at": "2026-06-06T12:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## SSE streaming and reconnection

### Ask / resume streams

- `POST /api/copilot/conversations/{conversation_id}/ask`
- `POST /api/copilot/conversations/{conversation_id}/resume`

Both support the `Last-Event-ID` header. When present, stored events after that ID are replayed first. Live events include monotonic `id:` fields for browser reconnection.

### Reconnect-only stream

`GET /api/copilot/conversations/{conversation_id}/stream`

| Parameter / header | Description |
|--------------------|-------------|
| `Last-Event-ID` | Resume after this event ID |
| `last_event_id` | Query fallback for the same value |
| `thread_id` | Must match `conversation_id` when provided |

Behavior:

1. Replay persisted events from `copilot_sse_events` with `event_id > Last-Event-ID`
2. If the conversation `stream_active` flag is true, poll for new events until the stream completes
3. No duplicate events across reconnects

## MongoDB indexes

Created at startup via `initialize_copilot_collections()`.

### `copilot_conversation_checkpoints`

| Index | Keys | Unique |
|-------|------|--------|
| `uniq_conversation_id` | `conversation_id` | yes |
| `idx_repo_updated` | `repository_id`, `updated_at` | no |
| `idx_user_repo_updated` | `user_id`, `repository_id`, `updated_at` | no |
| `idx_execution_updated` | `execution_id`, `updated_at` | no |
| `idx_status_repo` | `status`, `repository_id` | no |

### `copilot_approvals`

| Index | Keys | Unique |
|-------|------|--------|
| `uniq_approval_id` | `approval_id` | yes |
| `idx_pending_repo_created` | `status`, `repository_id`, `recorded_at` | no |
| `idx_conversation_created` | `conversation_id`, `recorded_at` | no |

### `copilot_sse_events`

| Index | Keys | Unique |
|-------|------|--------|
| `uniq_conversation_event_id` | `conversation_id`, `event_id` | yes |
| `idx_thread_event` | `thread_id`, `event_id` | no |

### `copilot_langgraph_checkpoints`

| Index | Keys | Unique |
|-------|------|--------|
| `idx_thread_checkpoint` | `thread_id`, `checkpoint_id` | no |

### `peil_executions` (existing ARIL indexes)

Relevant navigation indexes already defined in `peil/store/indexes.py`:

- `uniq_execution_id` on `execution_id`
- `idx_repo_subject_created` on `repository_id`, `subject_id`, `created_at`
- `idx_execution_status` on `status`
