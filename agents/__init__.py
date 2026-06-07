# Agents package for Gatekeeper

from agents.context import AgentContext, ContextBuilder
from agents.registry import ToolRegistry, build_default_registry
from agents.base_tool import BaseTool, LocalTool, ToolResult
from agents.mcp_wrappers import GitLabMCPTool, MongoMCPTool, DynatraceMCPTool, GitNexusMCPTool
from agents.adapter import GeminiToolAdapter
from agents.observability import ToolExecutionEvent, record_tool_event
from agents.planner import Planner, PlannerAgent
from agents.executor import Executor, ExecutorAgent
from agents.memory import MemoryStore
from agents.engine import WorkflowEngine
from agents.reflection import ReflectionLayer
from agents.approval import HumanApprovalLayer
from agents.recovery import FailureRecoveryManager
from agents.workflows import run_mr_review_workflow, run_incident_workflow, run_auto_remediation_workflow

# Import new MR review enhancement tools
from agents.tools import (
    validate_mr_webhook,
    validate_mr_webhook_schema,
    post_loading_indicator,
    post_loading_indicator_schema,
    update_review_comment,
    update_review_comment_schema,
    update_commit_status,
    update_commit_status_schema,
    track_progress,
    track_progress_schema
)

__all__ = [
    "AgentContext",
    "ContextBuilder",
    "ToolRegistry",
    "build_default_registry",
    "BaseTool",
    "LocalTool",
    "ToolResult",
    "GitLabMCPTool",
    "MongoMCPTool",
    "DynatraceMCPTool",
    "GitNexusMCPTool",
    "GeminiToolAdapter",
    "ToolExecutionEvent",
    "record_tool_event",
    "Planner",
    "PlannerAgent",
    "Executor",
    "ExecutorAgent",
    "MemoryStore",
    "WorkflowEngine",
    "ReflectionLayer",
    "HumanApprovalLayer",
    "FailureRecoveryManager",
    "run_mr_review_workflow",
    "run_incident_workflow",
    "run_auto_remediation_workflow",
    "validate_mr_webhook",
    "validate_mr_webhook_schema",
    "post_loading_indicator",
    "post_loading_indicator_schema",
    "update_review_comment",
    "update_review_comment_schema",
    "update_commit_status",
    "update_commit_status_schema",
    "track_progress",
    "track_progress_schema"
]

