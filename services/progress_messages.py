"""
User-friendly progress messages for merge request analysis.

Maps technical step names to engaging messages with emojis
for better user experience during analysis.
"""
from typing import Dict, Optional


# Mapping of technical steps to user-friendly messages with emojis
PROGRESS_MESSAGES: Dict[str, str] = {
    # Initial steps
    "received": "🔔 Merge request received - preparing for analysis",
    "starting": "🚀 Gatekeeper security analysis started",
    "fetching": "📡 Retrieving code changes from GitLab",
    "diff_fetched": "✅ Code changes retrieved successfully",

    # Repository operations
    "clone_running": "📥 Cloning repository for analysis",
    "clone_completed": "✅ Repository cloned successfully",
    "clone_failed": "⚠️ Repository clone encountered an issue - continuing with available data",

    # Schema inspection
    "schema_check_running": "🗄️ Examining database schema for potential issues",
    "schema_check_completed": "✅ Database schema analysis complete",
    "schema_check_skipped": "ℹ️ Schema inspection skipped - no database changes detected",

    # GitNexus tool operations - user-friendly alternatives
    "gitnexus_grep": "🔍 Searching codebase for relevant patterns",
    "gitnexus_file": "📖 Reading file contents for context",
    "gitnexus_query": "🔎 Querying codebase for specific patterns",
    "gitnexus_impact": "📊 Analyzing code impact and dependencies",
    "gitnexus_context": "🔬 Examining code context and relationships",
    "gitnexus_detect_changes": "🔍 Mapping code changes to affected components",

    # Impact analysis
    "impact_analysis_running": "📊 Analyzing code impact and dependencies",
    "impact_analysis_completed": "✅ Impact analysis complete",

    # AI analysis - more granular progress
    "ai_analysis_starting": "🤖 Initializing AI code review...",
    "ai_analysis_running": "🤖 Running AI-powered security and code quality review",
    "ai_analysis_thinking": "🧠 Analyzing code patterns and potential issues...",
    "ai_analysis_synthesizing": "📝 Synthesizing findings into report...",
    "ai_analysis_completed": "✅ AI analysis complete - {char_count} characters of findings generated",

    # Tool-specific progress messages (without exposing tool names)
    "tool_mapping_changes": "🔍 Mapping code changes to affected components...",
    "tool_analyzing_impact": "📊 Analyzing dependency impact across codebase...",
    "tool_examining_context": "🔬 Examining code context and relationships...",
    "tool_searching_references": "🔎 Searching for code references and patterns...",
    "tool_reading_file": "📖 Reading file contents for deeper analysis...",
    "tool_generic": "🔍 Gathering additional context for thorough review...",
    "tool_processing": "⚙️ Processing analysis results...",

    # Auto-fix
    "auto_fix_running": "🔧 Analyzing issues for automatic fixes",
    "auto_fix_completed": "✅ Auto-fix analysis complete",
    "auto_fix_skipped": "ℹ️ Auto-fix skipped - no fixable issues found",
    "auto_fix_error": "⚠️ Auto-fix encountered an error - skipping",

    # Report generation
    "report_generating": "📝 Generating comprehensive review report",
    "report_posting": "📤 Publishing report to merge request",
    "report_completed": "✅ Report published successfully",

    # Completion
    "completed": "🎉 Review completed successfully - Report published on GitLab",
    "failed": "❌ Analysis failed - please check the logs for details",

    # Generic fallback messages
    "processing": "🔄 Processing your request...",
    "analyzing": "🔬 Analyzing code...",
    "waiting": "⏳ Waiting for analysis to complete...",
}


# Map GitNexus tool names to user-friendly progress messages
# Format: "tool_name -> detailed_ci_cd_style_message"
TOOL_PROGRESS_MESSAGES: Dict[str, str] = {
    "detect_changes": "tool_mapping_changes",
    "impact": "tool_analyzing_impact",
    "context": "tool_examining_context",
    "query": "tool_searching_references",
    "gitnexus_grep": "tool_searching_references",
    "gitnexus_file": "tool_reading_file",
    "cypher": "tool_searching_references",
    "route_map": "tool_examining_context",
    "shape_check": "tool_examining_context",
    "api_impact": "tool_analyzing_impact",
}


# CI/CD-style step descriptions with more detail
CI_STEP_MESSAGES: Dict[str, str] = {
    # Repository steps
    "clone_running": "→ Cloning repository to workspace",
    "clone_completed": "✓ Repository clone completed",

    # Schema steps
    "schema_check_running": "→ Scanning diff for database schema changes",
    "schema_check_completed": "✓ Schema inspection completed",
    "schema_check_skipped": "⊘ No database changes detected, skipping",

    # GitNexus tool steps (detailed - running)
    "tool_mapping_changes": "→ Running detect_changes: Mapping diff to affected code paths",
    "tool_analyzing_impact": "→ Running impact: Analyzing dependency blast radius",
    "tool_examining_context": "→ Running context: Getting 360° symbol view",
    "tool_searching_references": "→ Running query: Searching codebase for references",
    "tool_reading_file": "→ Running file: Reading file contents for analysis",
    "tool_generic": "→ Gathering additional context from codebase",
}


# CI/CD-style completion messages
CI_COMPLETED_MESSAGES: Dict[str, str] = {
    # GitNexus tool steps (detailed - completed)
    "tool_mapping_changes": "✓ detect_changes completed: Found affected code paths",
    "tool_analyzing_impact": "✓ impact completed: Dependency analysis finished",
    "tool_examining_context": "✓ context completed: Retrieved symbol details",
    "tool_searching_references": "✓ query completed: Search results gathered",
    "tool_reading_file": "✓ file completed: File contents retrieved",
    "tool_generic": "✓ Context gathering completed",
}


def get_user_friendly_message(step: str, **kwargs) -> str:
    """
    Get a user-friendly message for a progress step.

    Args:
        step: The technical step identifier
        **kwargs: Optional parameters for message formatting

    Returns:
        User-friendly message with emoji
    """
    message = PROGRESS_MESSAGES.get(step)

    if not message:
        # Fallback for unknown steps - make it generic but friendly
        return "🔄 Processing your request..."

    # Simple template substitution for common kwargs
    # This allows for dynamic messages like "Found 5 issues"
    if kwargs:
        try:
            message = message.format(**kwargs)
        except (KeyError, ValueError):
            # If formatting fails, return the base message
            pass

    return message


def get_message_category(step: str) -> str:
    """
    Get the category for a progress step for styling purposes.

    Categories:
        - running: Currently in progress (blue)
        - success: Completed successfully (green)
        - error: Failed or error state (red)
        - info: General information (gray)

    Args:
        step: The technical step identifier

    Returns:
        Category string for styling
    """
    if "error" in step or "failed" in step:
        return "error"
    elif step in {"completed", "clone_completed", "diff_fetched",
                 "schema_check_completed", "impact_analysis_completed",
                 "ai_analysis_completed", "auto_fix_completed",
                 "report_completed"}:
        return "success"
    elif "running" in step or "thinking" in step:
        return "running"
    return "info"


# Message categories for styling reference
MESSAGE_CATEGORIES = {
    "running": "Currently in progress",
    "success": "Completed successfully",
    "error": "Failed or error state",
    "info": "General information"
}
