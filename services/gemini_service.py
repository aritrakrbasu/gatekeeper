import os
import asyncio
import json
from pathlib import Path
from google import genai
from google.genai import types

# Initialize official Gemini AI Client
ai_client = genai.Client()

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(prompt_name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    else:
        print(f"[⚠️] Prompt file not found: {prompt_path}, using fallback")
        return "You are a senior code reviewer. Analyze the provided code changes for security, quality, and performance issues."


async def run_gemini_review(raw_diff_content: str, impact_context: str) -> str:
    """Sends MR unified diff stream to Gemini for automated security/quality review."""
    system_instruction = load_prompt("senior_pr_reviewer")
    
    review_prompt = f"""Review this raw pull request diff change stream:

{raw_diff_content}

{impact_context}
"""

    response = await asyncio.to_thread(
        ai_client.models.generate_content,
        model='gemini-3.5-flash',
        contents=review_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1
        )
    )
    return response.text


async def run_gemini_fix_analysis(audit_report: str, patch_summary: str) -> dict:
    """Invokes Gemini with structured JSON output to analyze and remediation patch hunks."""
    fix_prompt = (
        f"Review this software engineering audit report:\n\n{audit_report}\n\n"
        f"ANALYZE THESE ATOMIC PATCHES FOR FIXABLE ISSUES:\n\n"
        f"{patch_summary}\n\n"
        "TASK: Determine if the identified problems can be resolved automatically at the HUNK level.\n\n"
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

    fix_analysis = await asyncio.to_thread(
        ai_client.models.generate_content,
        model='gemini-3.5-flash',
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
