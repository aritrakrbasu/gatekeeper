"""CopilotGraph enumeration types."""

from __future__ import annotations

from enum import Enum


class QuestionType(str, Enum):
    WHY_ISSUE_RAISED = "why_issue_raised"
    WHY_TOOL_CALLED = "why_tool_called"
    WHAT_EVIDENCE = "what_evidence"
    WHAT_ALTERNATIVES = "what_alternatives"
    IS_FINDING_CORRECT = "is_finding_correct"
    INVESTIGATE_FURTHER = "investigate_further"
    UNKNOWN = "unknown"


class CopilotNodeName(str, Enum):
    QUESTION = "question"
    EXECUTION_RESOLVER = "execution_resolver"
    REPLAY_RETRIEVAL = "replay_retrieval"
    EVIDENCE_RETRIEVAL = "evidence_retrieval"
    RESOLVE_KNOWLEDGE = "resolve_knowledge"
    QUESTION_CLASSIFIER = "question_classifier"
    PLAN_INVESTIGATION = "plan_investigation"
    EXECUTE_INVESTIGATION_PLAN = "execute_investigation_plan"
    APPROVAL_GATE = "approval_gate"
    RESUME_EXECUTION = "resume_execution"
    LIVE_INVESTIGATION = "live_investigation"
    RESPONSE_GENERATOR = "response_generator"
    KNOWLEDGE_PROPOSAL = "knowledge_proposal"


class StreamEventType(str, Enum):
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    RESPONSE_CHUNK = "response_chunk"
    CHECKPOINT = "checkpoint"
    DONE = "done"
    ERROR = "error"
    KNOWLEDGE_PROPOSED = "knowledge_proposed"
    APPROVAL_REQUIRED = "approval_required"
    PLAN_STEP_COMPLETED = "plan_step_completed"
    INTERRUPTED = "interrupted"
