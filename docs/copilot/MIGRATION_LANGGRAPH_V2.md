# LangGraph Copilot v2 Migration Notes

## Overview

Copilot v2 replaces the linear `CopilotGraphRunner` with a checkpointed LangGraph
`StateGraph` while preserving:

- HTTP API contracts (`/api/copilot/conversations`, `/ask`, GET checkpoint)
- `StreamEventType` SSE events
- JWT auth and repository scoping
- v1 node logic (`ReplayService`, `KnowledgeResolver`, read-only `ToolRegistry`)

WorkflowEngine remains imperative; only the Copilot runtime migrates to LangGraph.

## Phase 0 (prerequisites)

| Change | Location |
|--------|----------|
| `GraphBuilder.build_and_persist()` on terminal execution | `agents/engine.py` → `_maybe_build_decision_graph` |
| `bootstrap_copilot_execution()` for copilot ARIL sessions | `agents/aril_bridge.py` |
| LangGraph dependencies | `requirements.txt` |

Graph build runs on `completed` / `failed`, and on `awaiting_approval` when
`ARIL_GRAPH_BUILD_ON_PAUSE=true` (default).

## Phase 1–2 (v2 runtime)

New packages:

```
copilot/graph/v2/     state.py, builder.py, compile.py, routing.py, streaming.py
copilot/checkpoint/   langgraph_saver.py
```

| Concern | Implementation |
|---------|----------------|
| State | `CopilotGraphState` (`copilot`, `sse_events`, `halted`) |
| Checkpoints | `MongoLangGraphSaver` — `thread_id = conversation_id` |
| Conversation API state | `CheckpointRepository` (`copilot_conversation_checkpoints`) |
| Runner | `CopilotLangGraphRunner` in `streaming.py` |

Each ask deletes the LangGraph thread checkpoint before running (v1 parity: full
pipeline per question). LangGraph checkpoints persist **within** a single ask for
durability; conversation state between asks uses `CheckpointRepository`.

## Feature flags

| Variable | Default | Effect |
|----------|---------|--------|
| `COPILOT_LANGGRAPH_ENABLED` | `false` | Use LangGraph v2 runner in `CopilotService` |
| `COPILOT_V1_FALLBACK` | `true` | Allow rollback to `CopilotGraphRunner` when v2 disabled |

Enable v2:

```bash
export COPILOT_LANGGRAPH_ENABLED=true
```

Disable v1 fallback (v2 only):

```bash
export COPILOT_LANGGRAPH_ENABLED=true
export COPILOT_V1_FALLBACK=false
```

## Phase 3–4 (knowledge routing + investigation planning)

| Node | Purpose |
|------|---------|
| `resolve_knowledge` | `KnowledgeResolver` → citations + `knowledge_manifest` (persisted per turn) |
| `plan_investigation` | Deterministic `InvestigationPlan` (no tool execution yet) |

Graph path:

```
evidence_retrieval → resolve_knowledge → question_classifier
  → plan_investigation (when applicable) → response_generator → knowledge_proposal
```

Investigation profiles: `finding_challenge`, `repository_comparison`, `deep_investigation`.

Sample plans: `copilot/planning/samples/*.json`.

## Phase 5–6 (tool execution, interrupts, cutover)

| Capability | Implementation |
|------------|----------------|
| Tool execution | `execute_investigation_plan` via shared `ToolRegistry` |
| Risk categories | `copilot/tools/categories.py` — SAFE_READ, INVESTIGATE, MUTATING, DESTRUCTIVE |
| Interrupts | `approval_gate` uses LangGraph `interrupt()` |
| Resume API | `POST /api/copilot/conversations/{id}/resume` (+ `/resume/sync`) |
| Approval store | `copilot_approvals` collection |
| ARIL events | `approval_required`, `approval_granted`, `approval_rejected`, `approval_modified` |
| Default runtime | `COPILOT_LANGGRAPH_ENABLED=true`, `COPILOT_V1_FALLBACK=false` |

Sample flows: `copilot/approval/samples/*.json`

## Not in scope (later phases)
- Mutating tool execution approval
- Full copilot ARIL capture on turn complete (bootstrap exists; capture wiring is Phase 5)

## Rollback

1. Set `COPILOT_LANGGRAPH_ENABLED=false` (keep `COPILOT_V1_FALLBACK=true`).
2. Restart the API process.
3. Existing `copilot_conversation_checkpoints` documents remain compatible; v1 reads them unchanged.

## Deprecation path

1. Run parity tests: `tests/integration/test_copilot_langgraph_v2.py`
2. Enable v2 in staging (`COPILOT_LANGGRAPH_ENABLED=true`)
3. After soak period, set `COPILOT_V1_FALLBACK=false`
4. Remove `copilot/graph/runner.py` in a follow-up release

## Mongo collections

| Collection | Purpose |
|------------|---------|
| `copilot_conversation_checkpoints` | API-facing conversation state (unchanged) |
| `copilot_langgraph_checkpoints` | LangGraph checkpoint tuples |
| `copilot_langgraph_writes` | LangGraph pending writes |

## Testing

```bash
python -m pytest tests/unit/copilot/v2 tests/integration/test_copilot_langgraph_v2.py -v
python -m pytest tests/unit tests/integration -v
```
