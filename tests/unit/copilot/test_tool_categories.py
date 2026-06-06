"""Unit tests for Copilot tool risk categories."""

from copilot.tools.categories import (
    ToolRiskCategory,
    classify_tool,
    executes_immediately,
    requires_admin,
    requires_approval,
)


def test_safe_read_executes_immediately():
    category = classify_tool("get_gitlab_mr_diffs")
    assert category == ToolRiskCategory.SAFE_READ
    assert executes_immediately(category)
    assert not requires_approval(category)


def test_investigate_executes_immediately():
    category = classify_tool("gitnexus_analyze")
    assert category == ToolRiskCategory.INVESTIGATE
    assert executes_immediately(category)


def test_mutating_requires_approval():
    category = classify_tool("post_gitlab_mr_comment")
    assert category == ToolRiskCategory.MUTATING
    assert requires_approval(category)
    assert not executes_immediately(category)


def test_destructive_requires_admin():
    category = classify_tool("create_hotfix_branch_and_mr")
    assert category == ToolRiskCategory.DESTRUCTIVE
    assert requires_admin(category)
