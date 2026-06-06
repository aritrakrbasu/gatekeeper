"""ARIL enumeration types."""

from enum import Enum


class CaptureEventType(str, Enum):
    EXECUTION_STARTED = "execution_started"
    PLAN_EMITTED = "plan_emitted"
    PLAN_REVISED = "plan_revised"
    MODEL_TURN = "model_turn"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    REFLECTION_EVALUATED = "reflection_evaluated"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_MODIFIED = "approval_modified"
    APPROVAL_RESOLVED = "approval_resolved"
    EXECUTION_PAUSED = "execution_paused"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"


class ExecutionType(str, Enum):
    MR_REVIEW = "mr_review"
    INCIDENT = "incident"
    REMEDIATION = "remediation"
    COPILOT_INVESTIGATE = "copilot_investigate"


class ExecutionSource(str, Enum):
    WORKFLOW_ENGINE = "workflow_engine"
    LANGGRAPH_COPILOT = "langgraph_copilot"


class ExecutionStatus(str, Enum):
    CAPTURING = "capturing"
    GRAPH_BUILT = "graph_built"
    COMPLETE = "complete"
    PARTIAL = "partial"
    PAUSED = "paused"
    FAILED = "failed"


class SubjectType(str, Enum):
    MR = "mr"
    INCIDENT = "incident"
    CONVERSATION = "conversation"
    REPOSITORY = "repository"


class GraphNodeType(str, Enum):
    EXECUTION = "execution"
    PLAN = "plan"
    PLAN_STRATEGY = "plan_strategy"
    PLAN_STEP = "plan_step"
    PLAN_REVISION = "plan_revision"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MODEL_TURN = "model_turn"
    REFLECTION = "reflection"
    APPROVAL_GATE = "approval_gate"
    OBSERVATION = "observation"
    OUTCOME = "outcome"


class GraphEdgeRelation(str, Enum):
    TRIGGERS = "triggers"
    PRODUCES = "produces"
    VALIDATES = "validates"
    DEPENDS_ON = "depends_on"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    TRIGGERED_BY = "triggered_by"
    SUPERSEDES = "supersedes"


class OutcomeProfile(str, Enum):
    MR_REVIEW = "mr_review"
    INCIDENT = "incident"
    REMEDIATION = "remediation"
    COPILOT_INVESTIGATE = "copilot_investigate"
    NONE = "none"
