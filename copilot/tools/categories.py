"""Tool risk categories for Copilot investigation execution."""

from __future__ import annotations

from enum import Enum


class ToolRiskCategory(str, Enum):
    SAFE_READ = "safe_read"
    INVESTIGATE = "investigate"
    MUTATING = "mutating"
    DESTRUCTIVE = "destructive"


# Shared with WorkflowEngine ToolRegistry — single source of tool names.
_TOOL_CATEGORY_MAP: dict[str, ToolRiskCategory] = {
    "get_gitlab_mr_diffs": ToolRiskCategory.SAFE_READ,
    "run_schema_inspection": ToolRiskCategory.SAFE_READ,
    "get_dynatrace_incident_details": ToolRiskCategory.SAFE_READ,
    "clone_repo": ToolRiskCategory.INVESTIGATE,
    "gitnexus_analyze": ToolRiskCategory.INVESTIGATE,
    "run_impact_analysis": ToolRiskCategory.INVESTIGATE,
    "post_gitlab_mr_comment": ToolRiskCategory.MUTATING,
    "apply_hotfix_patch": ToolRiskCategory.MUTATING,
    "create_hotfix_branch_and_mr": ToolRiskCategory.DESTRUCTIVE,
}


def classify_tool(tool_name: str) -> ToolRiskCategory:
    return _TOOL_CATEGORY_MAP.get(tool_name, ToolRiskCategory.INVESTIGATE)


def executes_immediately(category: ToolRiskCategory) -> bool:
    return category in {ToolRiskCategory.SAFE_READ, ToolRiskCategory.INVESTIGATE}


def requires_approval(category: ToolRiskCategory) -> bool:
    return category in {ToolRiskCategory.MUTATING, ToolRiskCategory.DESTRUCTIVE}


def requires_admin(category: ToolRiskCategory) -> bool:
    return category == ToolRiskCategory.DESTRUCTIVE
