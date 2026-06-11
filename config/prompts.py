"""
Centralized prompt loading utilities for Arize AX integration.

This module provides convenient functions for loading prompts from Arize AX
with proper fallback mechanisms and formatting support for template variables.

Usage:
    from config.prompts import load_code_review_prompt, load_and_format_prompt

    # Load a static prompt
    system_instruction = await load_code_review_prompt(label="production")

    # Load and format a template prompt
    review_prompt = await load_and_format_prompt(
        "review_template",
        raw_diff_content=diff,
        impact_context=context
    )
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def load_prompt(
    prompt_id: str,
    label: str = "production",
    fallback: Optional[str] = None
) -> str:
    """
    Load a prompt from Arize AX with fallback support.

    Args:
        prompt_id: ID of the prompt to load (e.g., "senior_pr_reviewer")
        label: Prompt label to fetch (default: "production")
        fallback: Fallback prompt string if Arize AX unavailable

    Returns:
        Prompt content string

    Raises:
        Exception: If prompt cannot be loaded and no fallback provided
    """
    from config.arize_ax_client import get_ax_client

    ax_client = await get_ax_client()

    try:
        prompt = await ax_client.get_prompt(prompt_id, label=label)
        if prompt:
            return prompt
    except Exception as e:
        logger.warning(f"[WARN] Failed to load prompt '{prompt_id}' from Arize AX: {e}")

    if fallback:
        logger.info(f"[INFO] Using fallback for prompt '{prompt_id}'")
        return fallback

    raise Exception(f"Failed to load prompt '{prompt_id}' and no fallback provided")


async def load_and_format_prompt(
    prompt_id: str,
    label: str = "production",
    **kwargs
) -> str:
    """
    Load a template prompt from Arize AX and format with variables.

    Args:
        prompt_id: ID of the prompt template to load
        label: Prompt label to fetch (default: "production")
        **kwargs: Template variables to substitute in the prompt

    Returns:
        Formatted prompt string

    Example:
        prompt = await load_and_format_prompt(
            "review_template",
            raw_diff_content=diff,
            impact_context=context
        )
    """
    prompt_template = await load_prompt(prompt_id, label=label)

    try:
        return prompt_template.format(**kwargs)
    except KeyError as e:
        missing_var = str(e).strip("'")
        raise Exception(
            f"Template variable '{missing_var}' not provided for prompt '{prompt_id}'. "
            f"Expected variables based on template: {list(_extract_template_vars(prompt_template))}"
        )
    except Exception as e:
        raise Exception(f"Failed to format prompt template '{prompt_id}': {e}")


def _extract_template_vars(template: str) -> set:
    """Extract template variable names from a prompt template."""
    import re
    return set(re.findall(r'\{([^}]+)\}', template))


# ============================================================================
# Convenience functions for specific prompt categories
# ============================================================================

async def load_code_review_prompt(label: str = "production") -> str:
    """
    Load the main code review system instruction prompt.

    Args:
        label: Prompt label to fetch (default: "production")

    Returns:
        Code review system instruction
    """
    return await load_prompt("senior_pr_reviewer", label=label)


async def load_planner_prompt(
    workflow_type: str,
    label: str = "production"
) -> str:
    """
    Load a planner system instruction prompt based on workflow type.

    Args:
        workflow_type: Type of workflow ("sentry", "mr_review", "dynatrace")
        label: Prompt label to fetch (default: "production")

    Returns:
        Planner system instruction for the specified workflow
    """
    prompt_ids = {
        "sentry": "sentry_planner",
        "mr_review": "mr_review_planner",
        "dynatrace": "dynatrace_planner"
    }

    if workflow_type not in prompt_ids:
        raise ValueError(
            f"Unknown workflow type '{workflow_type}'. "
            f"Must be one of: {list(prompt_ids.keys())}"
        )

    return await load_prompt(prompt_ids[workflow_type], label=label)


async def load_eval_prompt(
    eval_type: str,
    label: str = "production"
) -> str:
    """
    Load an evaluation prompt based on evaluation type.

    Args:
        eval_type: Type of evaluation ("security", "quality", "actionability",
                    "clarity", "completeness", "correctness")
        label: Prompt label to fetch (default: "production")

    Returns:
        Evaluation prompt for the specified type
    """
    prompt_ids = {
        "security": "eval_security",
        "quality": "eval_quality",
        "actionability": "eval_actionability",
        "clarity": "eval_clarity",
        "completeness": "eval_completeness",
        "correctness": "eval_correctness"
    }

    if eval_type not in prompt_ids:
        raise ValueError(
            f"Unknown evaluation type '{eval_type}'. "
            f"Must be one of: {list(prompt_ids.keys())}"
        )

    return await load_prompt(prompt_ids[eval_type], label=label)


# ============================================================================
# Category-specific prompt loading functions
# ============================================================================

# Code Review Prompts
async def load_code_review_fallback(label: str = "production") -> str:
    """Load fallback code review prompt."""
    return await load_prompt("code_review_fallback", label=label)


async def load_review_template(label: str = "production") -> str:
    """Load review template prompt (unformatted)."""
    return await load_prompt("review_template", label=label)


async def load_gitnexus_review_enhanced(label: str = "production") -> str:
    """Load GitNexus-enhanced review prompt."""
    return await load_prompt("gitnexus_review_enhanced", label=label)


async def load_fix_analysis(label: str = "production") -> str:
    """Load fix analysis prompt."""
    return await load_prompt("fix_analysis", label=label)


# Incident Management Prompts
async def load_diagnosis_instruction(label: str = "production") -> str:
    """Load production crash diagnosis instruction."""
    return await load_prompt("diagnosis_instruction", label=label)


async def load_remediation_instruction(label: str = "production") -> str:
    """Load automated patch generation instruction."""
    return await load_prompt("remediation_instruction", label=label)


# Fix Generation Prompts
async def load_fix_generation_system(label: str = "production") -> str:
    """Load fix generation system instruction."""
    return await load_prompt("fix_generation_system", label=label)


async def load_fix_generation_template(label: str = "production") -> str:
    """Load fix generation template prompt (unformatted)."""
    return await load_prompt("fix_generation_template", label=label)


# Impact Analysis Prompts
async def load_impact_analysis_system(label: str = "production") -> str:
    """Load impact analysis system instruction."""
    return await load_prompt("impact_analysis_system", label=label)


async def load_impact_analysis_template(label: str = "production") -> str:
    """Load impact analysis template prompt (unformatted)."""
    return await load_prompt("impact_analysis_template", label=label)


# Self-Improvement Prompts
async def load_prompt_modification(label: str = "production") -> str:
    """Load prompt modification template prompt (unformatted)."""
    return await load_prompt("prompt_modification", label=label)


# ============================================================================
# Prompt ID registry for reference
# ============================================================================

PROMPT_REGISTRY = {
    # Code Review Prompts
    "senior_pr_reviewer": "Main system instruction for PR code reviews",
    "code_review_fallback": "Fallback prompt when main unavailable",
    "review_template": "Review prompt with diff content (vars: raw_diff_content, impact_context)",
    "gitnexus_review_enhanced": "GitNexus-enhanced review with tool instructions",
    "fix_analysis": "Fix analysis with JSON output requirements",

    # Incident Management Prompts
    "diagnosis_instruction": "Production crash diagnosis instruction",
    "remediation_instruction": "Automated patch generation instruction",

    # Planner Prompts
    "sentry_planner": "System instruction for Sentry bug fixing workflows",
    "mr_review_planner": "System instruction for MR review workflows",
    "dynatrace_planner": "System instruction for Dynatrace workflows",

    # Fix Generation Prompts
    "fix_generation_system": "System instruction for bug remediation",
    "fix_generation_template": "Fix generation with Sentry context (vars: sentry_issue_id, analysis, file_path)",

    # Impact Analysis Prompts
    "impact_analysis_system": "System instruction for impact analysis",
    "impact_analysis_template": "Analysis prompt template (vars: diff_content, blast_radius)",

    # Evaluation Prompts
    "eval_security": "Security vulnerability coverage evaluation",
    "eval_quality": "Code quality coverage evaluation",
    "eval_actionability": "Review actionability evaluation",
    "eval_clarity": "Review clarity evaluation",
    "eval_completeness": "Review completeness evaluation",
    "eval_correctness": "Review correctness evaluation",

    # Self-Improvement
    "prompt_modification": "Template for prompt improvement (vars: prompt, modifications)"
}


def list_all_prompts() -> dict:
    """
    Get a dictionary of all registered prompts with their descriptions.

    Returns:
        Dictionary mapping prompt IDs to descriptions
    """
    return PROMPT_REGISTRY.copy()


def get_prompt_info(prompt_id: str) -> Optional[str]:
    """
    Get description for a specific prompt ID.

    Args:
        prompt_id: ID of the prompt

    Returns:
        Prompt description or None if not found
    """
    return PROMPT_REGISTRY.get(prompt_id)
