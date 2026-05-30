import os
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict
from google import genai
from google.genai import types
from google.genai.errors import APIError
from opentelemetry import trace, context
from datetime import datetime

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
                print(f"[WARN] Gemini API transient error ({code or 'unknown'}): {e}. Retrying attempt {attempt}/{max_retries} in {backoff:.2f}s...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"[ERROR] Gemini API non-transient or final attempt error: {e}")
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
                print(f"[WARN] Gemini API unexpected transient error: {e}. Retrying attempt {attempt}/{max_retries} in {backoff:.2f}s...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"[ERROR] Gemini API error: {e}")
                raise


def load_prompt(prompt_name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    else:
        print(f"[WARN] Prompt file not found: {prompt_path}, using fallback")
        return "You are a senior code reviewer. Analyze the provided code changes for security, quality, and performance issues."


async def track_llm_usage(
    user_id: str,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    operation_type: str = "review",
    mr_id: Optional[str] = None,
    repository_id: Optional[str] = None,
    trace_id: Optional[str] = None
):
    """
    Track LLM usage to MongoDB for billing.

    This stores usage data directly to MongoDB when an LLM call is made,
    ensuring billing data is captured even if Arize sync fails.

    Args:
        user_id: User who made the request
        model_name: Model used (e.g., "gemini-3.5-flash")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        total_tokens: Total tokens
        operation_type: Type of operation (review, fix_analysis, etc.)
        mr_id: Optional MR ID
        repository_id: Optional repository ID
        trace_id: Optional trace ID from Arize
    """
    try:
        from services.mongo_client import upsert_one
        from services.pricing import calculate_cost
        from services.billing_service import _update_billing_cycle_summary

        # Calculate cost
        estimated_cost = await calculate_cost(model_name, input_tokens, output_tokens)

        # Get current billing cycle
        now = datetime.utcnow()
        billing_cycle = now.strftime("%Y-%m")

        # Store usage record
        record = {
            "user_id": user_id,
            "trace_id": trace_id or f"local-{now.strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": now,
            "billing_cycle": billing_cycle,
            "model_name": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": estimated_cost,
            "metadata": {
                "mr_id": mr_id,
                "repository_id": repository_id,
                "operation_type": operation_type
            },
            "synced_at": now
        }

        # Upsert to MongoDB
        success = await upsert_one(
            "llm_usage_records",
            {"user_id": user_id, "trace_id": record["trace_id"]},
            record
        )

        if success:
            print(f"[OK] Stored usage record: {input_tokens}+{output_tokens} tokens, ${estimated_cost:.6f}")

            # Update billing cycle summary
            await _update_billing_cycle_summary(user_id, billing_cycle)
        else:
            print(f"[WARN] Failed to store usage record")

    except Exception as e:
        print(f"[ERROR] Failed to track LLM usage: {e}")
        # Don't raise - tracking failures shouldn't break the main flow


async def run_gemini_review(raw_diff_content: str, impact_context: str, user_config: Dict = None, user_id: str = None, mr_id: str = None, repository_id: str = None) -> dict:
    """
    Sends MR unified diff stream to Gemini for automated security/quality review.

    Args:
        raw_diff_content: The code diff to review
        impact_context: Impact analysis context
        user_config: Optional dict with user's Gemini config (api_token, model)
                     If not provided, uses default client and model
        user_id: Optional user ID for usage tracking and Arize tracing
        mr_id: Optional MR ID for trace attribution
        repository_id: Optional repository ID for trace attribution

    Returns:
        dict with "review_text" (str) and "usage" (dict with token counts and model)
    """
    system_instruction = load_prompt("senior_pr_reviewer")

    review_prompt = f"""Review this raw pull request diff change stream:

{raw_diff_content}

{impact_context}
"""

    # Get tracer for creating manual span
    tracer = trace.get_tracer(__name__)

    # Use OpenTelemetry baggage to propagate attributes to all child spans
    # Baggage is specifically designed for cross-boundary context propagation
    from opentelemetry.trace import set_span_in_context
    from opentelemetry.baggage import set_baggage
    from opentelemetry.context import Context

    # Create baggage with our custom attributes (using OpenInference naming conventions)
    ctx = Context()
    if user_id:
        ctx = set_baggage("user.id", str(user_id), context=ctx)  # OpenInference convention
    if mr_id:
        ctx = set_baggage("mr.id", str(mr_id), context=ctx)  # Use dot notation
    if repository_id:
        ctx = set_baggage("repository.id", str(repository_id), context=ctx)  # Use dot notation
    ctx = set_baggage("operation.type", "review", context=ctx)

    # Create a manual span with the baggage context
    token = context.attach(ctx)
    try:
        with tracer.start_as_current_span("gemini_review_call") as parent_span:
            # Also set directly on span using OpenInference naming conventions
            if user_id:
                parent_span.set_attribute("user.id", str(user_id))
            if mr_id:
                parent_span.set_attribute("mr.id", str(mr_id))
            if repository_id:
                parent_span.set_attribute("repository.id", str(repository_id))
            parent_span.set_attribute("operation.type", "review")

            print(f"[INFO] Set parent span attributes: user_id={user_id}, mr_id={mr_id}, repository_id={repository_id}")

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

            # After the LLM call, find and update the instrumented LLM span with user context
            # The instrumentation creates a child span for the LLM call
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                # Check if this is the instrumented LLM span (has llm attributes)
                span_context = current_span.get_span_context()
                print(f"[INFO] Post-LLM current span: {span_context.span_id[:16]}...")

                # Set user context on the instrumented span as well
                # This ensures billing can find user_id on LLM spans
                if user_id:
                    current_span.set_attribute("user.id", str(user_id))
                if mr_id:
                    current_span.set_attribute("mr.id", str(mr_id))
                if repository_id:
                    current_span.set_attribute("repository.id", str(repository_id))
                current_span.set_attribute("operation.type", "review")
                print(f"[INFO] Set user context on instrumented LLM span")

    finally:
        context.detach(token)

    # Extract usage metadata from Gemini response
    usage_metadata = getattr(response, 'usage_metadata', None)
    usage_data = {
        "input_tokens": getattr(usage_metadata, 'prompt_token_count', 0) if usage_metadata else 0,
        "output_tokens": getattr(usage_metadata, 'candidates_token_count', 0) if usage_metadata else 0,
        "total_tokens": getattr(usage_metadata, 'total_token_count', 0) if usage_metadata else 0,
        "model_name": model
    }

    # Track usage to MongoDB for billing
    if user_id and usage_data.get("total_tokens", 0) > 0:
        await track_llm_usage(
            user_id=user_id,
            model_name=model,
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            operation_type="review",
            mr_id=mr_id,
            repository_id=repository_id
        )

    return {
        "review_text": response.text,
        "usage": usage_data
    }


async def run_gemini_fix_analysis(audit_report: str, patch_summary: str, schema_context: Optional[str] = None, user_config: Dict = None, user_id: str = None, mr_id: str = None, repository_id: str = None) -> dict:
    """
    Invokes Gemini with structured JSON output to analyze and remediation patch hunks.

    Args:
        audit_report: The security audit report
        patch_summary: Summary of atomic patches to analyze
        schema_context: Optional database schema context
        user_config: Optional dict with user's Gemini config (api_token, model)
        user_id: Optional user ID for usage tracking and Arize tracing
        mr_id: Optional MR ID for trace attribution
        repository_id: Optional repository ID for trace attribution

    Returns:
        dict with "fixable" (bool), "fixes" (list), and "usage" (dict with token counts)
    """
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

    # Get tracer for creating manual span
    tracer = trace.get_tracer(__name__)

    # Use OpenTelemetry baggage to propagate attributes to all child spans
    from opentelemetry.trace import set_span_in_context
    from opentelemetry.baggage import set_baggage
    from opentelemetry.context import Context

    # Create baggage with our custom attributes (using OpenInference naming conventions)
    ctx = Context()
    if user_id:
        ctx = set_baggage("user.id", str(user_id), context=ctx)  # OpenInference convention
    if mr_id:
        ctx = set_baggage("mr.id", str(mr_id), context=ctx)  # Use dot notation
    if repository_id:
        ctx = set_baggage("repository.id", str(repository_id), context=ctx)  # Use dot notation
    ctx = set_baggage("operation.type", "fix_analysis", context=ctx)

    # Create a manual span with the baggage context
    token = context.attach(ctx)
    try:
        with tracer.start_as_current_span("gemini_fix_analysis_call") as parent_span:
            # Also set directly on span using OpenInference naming conventions
            if user_id:
                parent_span.set_attribute("user.id", str(user_id))
            if mr_id:
                parent_span.set_attribute("mr.id", str(mr_id))
            if repository_id:
                parent_span.set_attribute("repository.id", str(repository_id))
            parent_span.set_attribute("operation.type", "fix_analysis")

            print(f"[INFO] Set parent span attributes: user_id={user_id}, mr_id={mr_id}, repository_id={repository_id}")

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

            # After the LLM call, find and update the instrumented LLM span with user context
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                span_context = current_span.get_span_context()
                print(f"[INFO] Post-LLM current span: {span_context.span_id[:16]}...")

                # Set user context on the instrumented span as well
                if user_id:
                    current_span.set_attribute("user.id", str(user_id))
                if mr_id:
                    current_span.set_attribute("mr.id", str(mr_id))
                if repository_id:
                    current_span.set_attribute("repository.id", str(repository_id))
                current_span.set_attribute("operation.type", "fix_analysis")
                print(f"[INFO] Set user context on instrumented LLM span")

    finally:
        context.detach(token)

    # Extract usage metadata from Gemini response
    usage_metadata = getattr(fix_analysis, 'usage_metadata', None)
    usage_data = {
        "input_tokens": getattr(usage_metadata, 'prompt_token_count', 0) if usage_metadata else 0,
        "output_tokens": getattr(usage_metadata, 'candidates_token_count', 0) if usage_metadata else 0,
        "total_tokens": getattr(usage_metadata, 'total_token_count', 0) if usage_metadata else 0,
        "model_name": model
    }

    # Track usage to MongoDB for billing
    if user_id and usage_data.get("total_tokens", 0) > 0:
        await track_llm_usage(
            user_id=user_id,
            model_name=model,
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            operation_type="fix_analysis",
            mr_id=mr_id,
            repository_id=repository_id
        )

    response_text = fix_analysis.text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    response_text = response_text.strip()

    # Parse JSON and add usage data
    fix_result = json.loads(response_text)
    fix_result["usage"] = usage_data

    return fix_result
