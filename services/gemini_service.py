import os
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict
from google import genai
from google.genai import types
from google.genai.errors import APIError

# Default client for when no user config is available
ai_client = genai.Client()


def create_user_client(api_token: str) -> genai.Client:
    """Create a Gemini client with user's API token."""
    return genai.Client(api_key=api_token)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


async def call_gemini_with_retry(func, *args, max_retries: int = 5, initial_backoff: float = 1.0, **kwargs):
    """Calls Gemini API function with exponential backoff on transient errors (503, 429, etc.)."""
    backoff = initial_backoff
    for attempt in range(1, max_retries + 1):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except APIError as e:
            code = getattr(e, "code", None)
            message = str(e)
            is_transient = (
                code in (429, 503) or
                "503" in message or
                "429" in message or
                "UNAVAILABLE" in message or
                "resource exhausted" in message.lower() or
                "high demand" in message.lower()
            )
            if is_transient and attempt < max_retries:
                print(f"[⚠️] Gemini API transient error ({code or 'unknown'}): {e}. Retrying attempt {attempt}/{max_retries} in {backoff:.2f}s...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"[❌] Gemini API non-transient or final attempt error: {e}")
                raise
        except Exception as e:
            message = str(e)
            is_transient_msg = (
                "503" in message or
                "429" in message or
                "UNAVAILABLE" in message or
                "resource exhausted" in message.lower() or
                "high demand" in message.lower()
            )
            if is_transient_msg and attempt < max_retries:
                print(f"[⚠️] Gemini API unexpected transient error: {e}. Retrying attempt {attempt}/{max_retries} in {backoff:.2f}s...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"[❌] Gemini API error: {e}")
                raise


def load_prompt(prompt_name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    else:
        print(f"[⚠️] Prompt file not found: {prompt_path}, using fallback")
        return "You are a senior code reviewer. Analyze the provided code changes for security, quality, and performance issues."


async def run_gemini_review(raw_diff_content: str, impact_context: str, user_config: Dict = None) -> str:
    """
    Sends MR unified diff stream to Gemini for automated security/quality review.

    Args:
        raw_diff_content: The code diff to review
        impact_context: Impact analysis context
        user_config: Optional dict with user's Gemini config (api_token, model)
                     If not provided, uses default client and model
    """
    system_instruction = load_prompt("senior_pr_reviewer")

    review_prompt = f"""Review this raw pull request diff change stream:

{raw_diff_content}

{impact_context}
"""

    # Use user's config if provided, otherwise use defaults
    client = ai_client
    model = 'gemini-3.5-flash'  # Default model

    if user_config:
        api_token = user_config.get("api_token")
        model = user_config.get("model", "gemini-3.5-flash")
        if api_token:
            client = create_user_client(api_token)
            print(f"[INFO] Using user's Gemini API with model: {model}")
        else:
            print(f"[WARN] User config provided but no API token, using defaults")
    else:
        print(f"[WARN] No user config provided, using default Gemini client")

    response = await call_gemini_with_retry(
        client.models.generate_content,
        model=model,
        contents=review_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1
        )
    )
    return response.text


async def run_gemini_fix_analysis(audit_report: str, patch_summary: str, schema_context: Optional[str] = None, user_config: Dict = None) -> dict:
    """Invokes Gemini with structured JSON output to analyze and remediation patch hunks."""
    schema_prefix = ""
    if schema_context:
        schema_prefix = (
            f"\n\n## Current Database Schema State (for fix reference)\n"
            f"Use this schema information to ensure your fix suggestions do not:\n"
            f"- Add fields that already exist with a different type\n"
            f"- Reference collection names that do not exist\n"
            f"- Suggest schema changes inconsistent with the current structure\n"
            f"{schema_context}\n"
        )

    fix_prompt = (
        f"Review this software engineering audit report:\n\n{audit_report}\n\n"
        f"ANALYZE THESE ATOMIC PATCHES FOR FIXABLE ISSUES:\n\n"
        f"{patch_summary}\n\n"
        f"{schema_prefix}"
        f"TASK: Determine if the identified problems can be resolved automatically at the HUNK level.\n\n"
        "FIXABLE ISSUES INCLUDE (but are not limited to):\n"
        "- Hardcoded secrets, API keys, passwords, tokens -> Extract to environment variables\n"
        "- Hardcoded configuration values -> Extract to environment variables\n"
        "- Insecure default values -> Replace with secure defaults or env vars\n"
        "- SQL injection vulnerabilities -> Use parameterized queries\n"
        "- Missing input validation -> Add validation logic\n"
        "- Insecure cryptographic algorithms -> Use secure alternatives\n"
        "- Sensitive data in logs -> Remove or sanitize\n\n"
        "For each fixable issue, provide:\n"
        "- hunk_id: The ID of the hunk to fix (from the patch summary above)\n"
        "- issue: Brief description of the problem\n"
        "- original_lines: The EXACT lines from the hunk that need to be fixed (preserve formatting)\n"
        "- fixed_lines: The corrected replacement lines\n"
        "- extracted_env_vars: If secrets/configs are extracted, map them as {\"VAR_NAME\": \"value\"}\n\n"
        "IMPORTANT RULES:\n"
        "1. Use the EXACT hunk_id from the patch summary above\n"
        "2. original_lines must match the hunk content exactly\n"
        "3. For hardcoded values, extract to environment variables using format: process.env.VAR_NAME (JavaScript) or os.getenv('VAR_NAME') (Python)\n"
        "4. If no issues are fixable, return {\"fixable\": false, \"fixes\": []}\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"fixable": true/false, "fixes": [{"hunk_id": "id", "issue": "description", "original_lines": ["line1", "line2"], "fixed_lines": ["line1_fixed", "line2_fixed"], "extracted_env_vars": {"KEY": "value"}}]}'
    )

    # Use user's config if provided, otherwise use defaults
    client = ai_client
    model = 'gemini-3.5-flash'  # Default model

    if user_config:
        api_token = user_config.get("api_token")
        model = user_config.get("model", "gemini-3.5-flash")
        if api_token:
            client = create_user_client(api_token)
            print(f"[INFO] Using user's Gemini API with model: {model}")
        else:
            print(f"[WARN] User config provided but no API token, using defaults")

    fix_analysis = await call_gemini_with_retry(
        client.models.generate_content,
        model=model,
        contents=fix_prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are a strict automated code repair system. Output only valid JSON with no markdown formatting.",
            temperature=0.1,
            response_mime_type="application/json"
        )
    )

    response_text = fix_analysis.text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    response_text = response_text.strip()

    return json.loads(response_text)
