import os
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from google import genai
from google.genai import types
from google.genai.errors import APIError
from opentelemetry import trace, context
from datetime import datetime
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Default client for when no user config is available
ai_client = genai.Client()

# Timeout for MCP tool calls
MCP_TIMEOUT = 30


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
        from services.billing_service import _update_billing_cycle_summary

        # Cost will be calculated from Arize traces during sync
        # Set to 0 for local fallback records
        estimated_cost = 0.0

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
    current_trace_id = None  # Initialize outside the try block
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
            llm_span_id = None  # Capture the LLM span ID for annotations
            if current_span and current_span.is_recording():
                # Check if this is the instrumented LLM span (has llm attributes)
                span_context = current_span.get_span_context()
                llm_span_id = format(span_context.span_id, 'x')  # Capture span ID as hex string
                print(f"[INFO] Post-LLM current span: {llm_span_id}...")

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

            # Capture trace_id while span is still active
            from ai_observability.trace_utils import get_current_trace_id
            current_trace_id = get_current_trace_id()
            if current_trace_id:
                print(f"[INFO] Captured trace_id for MR {mr_id}: {current_trace_id[:16]}...")
            else:
                print(f"[WARN] No active trace found during review - feedback linkage may not work")

    finally:
        context.detach(token)

    # Extract usage metadata from Gemini response
    try:
        usage_metadata = getattr(response, 'usage_metadata', None)

        usage_data = {
            "input_tokens": getattr(usage_metadata, 'prompt_token_count', 0) if usage_metadata else 0,
            "output_tokens": getattr(usage_metadata, 'candidates_token_count', 0) if usage_metadata else 0,
            "total_tokens": getattr(usage_metadata, 'total_token_count', 0) if usage_metadata else 0,
            "model_name": model
        }
    except Exception as metadata_err:
        print(f"[ERROR] Error extracting usage metadata: {metadata_err}")
        import traceback
        traceback.print_exc()
        usage_data = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model_name": model}

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

    try:
        review_text = response.text
    except Exception as text_err:
        print(f"[ERROR] Error accessing response.text: {text_err}")
        import traceback
        traceback.print_exc()
        review_text = "Error: Could not extract review text from Gemini response"

    return {
        "review_text": review_text,
        "usage": usage_data,
        "trace_id": current_trace_id,
        "span_id": llm_span_id  # Include LLM span ID for Arize annotations
    }


def convert_mcp_tools_to_gemini(mcp_tools) -> types.Tool:
    """
    Convert MCP tool schemas to Gemini native Tool format using the proper SDK types.
    Removes the 'repo' parameter so it can be injected automatically based on the project.
    """
    function_declarations = []

    for tool in mcp_tools:
        # MCP tools use standard JSON Schema in inputSchema
        schema = getattr(tool, 'inputSchema', {})
        if hasattr(schema, 'model_dump'):
            schema = schema.model_dump()
        elif not isinstance(schema, dict):
            schema = dict(schema)

        properties = schema.get('properties', {})
        required = schema.get('required', [])

        # Remove 'repo' parameter - we'll inject it automatically
        # This prevents Gemini from choosing the wrong repo
        properties = {k: v for k, v in properties.items() if k != 'repo'}
        required = [r for r in required if r != 'repo']

        # Map properties cleanly using types.Schema objects
        param_properties = {}
        for prop_name, prop_def in properties.items():
            param_properties[prop_name] = convert_mcp_property_to_gemini(prop_def)

        # Build the exact parameters definition
        parameters = types.Schema(
            type="OBJECT",
            properties=param_properties if param_properties else None,
            required=required if required else None
        )

        # Create native FunctionDeclaration object
        function_declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=parameters
            )
        )

    return types.Tool(function_declarations=function_declarations)


def convert_mcp_property_to_gemini(prop_def: dict) -> types.Schema:
    """
    Recursively convert an MCP parameter property into a Gemini types.Schema object.
    """
    if not isinstance(prop_def, dict):
        prop_def = dict(prop_def)

    prop_type = prop_def.get('type', 'string').upper()
    description = prop_def.get('description')

    # Handle Arrays
    if prop_type == 'ARRAY':
        items_def = prop_def.get('items', {"type": "string"})
        return types.Schema(
            type="ARRAY",
            description=description,
            items=convert_mcp_property_to_gemini(items_def)
        )

    # Handle Objects
    if prop_type == 'OBJECT':
        nested_properties = prop_def.get('properties', {})
        nested_required = prop_def.get('required', [])

        mapped_nested = {
            k: convert_mcp_property_to_gemini(v)
            for k, v in nested_properties.items()
        }

        return types.Schema(
            type="OBJECT",
            description=description,
            properties=mapped_nested,
            required=nested_required if nested_required else None
        )

    # Handle baseline types (STRING, INTEGER, NUMBER, BOOLEAN)
    if prop_type in ['NUMBER', 'FLOAT']:
        gemini_type = "NUMBER"
    elif prop_type in ['INTEGER', 'INT']:
        gemini_type = "INTEGER"
    elif prop_type == 'BOOLEAN':
        gemini_type = "BOOLEAN"
    else:
        gemini_type = "STRING"

    return types.Schema(
        type=gemini_type,
        description=description
    )


def map_json_type_to_gemini(json_type: str) -> str:
    """Map JSON Schema types to Gemini types. (Deprecated - use convert_mcp_property_to_gemini)"""
    type_map = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object"
    }
    return type_map.get(json_type, "string")


async def run_gemini_review_with_gitnexus(
    raw_diff_content: str,
    impact_context: str,
    repo_path: Optional[Path] = None,
    repo_name: Optional[str] = None,
    user_config: Dict = None,
    user_id: str = None,
    mr_id: str = None,
    repository_id: str = None
) -> dict:
    """
    Sends MR diff to Gemini with GitNexus MCP tools for dynamic impact analysis.

    This function spawns GitNexus as an MCP server and passes its tools to Gemini,
    allowing Gemini to call GitNexus tools (impact, detect_changes, context, query)
    dynamically when needed during the review.

    Args:
        raw_diff_content: The code diff to review
        impact_context: Impact analysis context
        repo_path: Path to the git repository
        repo_name: GitNexus repository name (required when multiple repos indexed)
        user_config: Optional dict with user's Gemini config (api_token, model)
        user_id: Optional user ID for usage tracking and Arize tracing
        mr_id: Optional MR ID for trace attribution
        repository_id: Optional repository ID for trace attribution

    Returns:
        dict with "review_text" (str), "usage" (dict), and "tools_called" (list)
    """
    system_instruction = load_prompt("senior_pr_reviewer")

    review_prompt = f"""Review this raw pull request diff change stream:

{raw_diff_content}

{impact_context}

You have access to GitNexus tools for advanced code intelligence:
- impact: Analyze blast radius and dependencies
- detect_changes: Map changed lines to affected processes
- context: Get 360-degree symbol view
- query: Search the codebase

Use these tools when you need more context about dependencies, call chains,
or the broader impact of the changes.

CRITICAL INSTRUCTION FOR THIS REVIEW:
Look closely at the diff. If any exported identifiers or configuration objects are renamed or modified, you MUST use the `query` or `impact` (downstream) tools to verify if references in other files (e.g., frontend entry points, `main.js`, etc.) are now broken. Do not output your final review until you have confirmed whether or not this change breaks other parts of the codebase.
"""

    # Get tracer for creating manual span
    tracer = trace.get_tracer(__name__)

    # Use OpenTelemetry baggage to propagate attributes
    from opentelemetry.baggage import set_baggage
    from opentelemetry.context import Context

    # Create baggage with our custom attributes
    ctx = Context()
    if user_id:
        ctx = set_baggage("user.id", str(user_id), context=ctx)
    if mr_id:
        ctx = set_baggage("mr.id", str(mr_id), context=ctx)
    if repository_id:
        ctx = set_baggage("repository.id", str(repository_id), context=ctx)
    ctx = set_baggage("operation.type", "review", context=ctx)

    token = context.attach(ctx)
    current_trace_id = None
    llm_span_id = None

    # Track aggregated metrics across multi-turn tool loops
    total_input_tokens = 0
    total_output_tokens = 0
    review_text = ""
    tools_called = []

    # Use user's config if provided, otherwise use defaults
    client = ai_client
    model = 'gemini-2.5-pro'  # Use Pro for structural dependency reasoning

    if user_config:
        api_token = user_config.get("api_token")
        model = user_config.get("model", "gemini-2.5-pro")
        if api_token:
            client = create_user_client(api_token)
            print(f"[INFO] Using user's Gemini API with model: {model}")
        else:
            print(f"[WARN] User config provided but no API token, using defaults")
    else:
        print(f"[WARN] No user config provided, using default Gemini client")

    # Set repo path - use current directory if not specified
    if repo_path is None:
        repo_path = Path.cwd()

    try:
        with tracer.start_as_current_span("gemini_review_with_gitnexus") as parent_span:
            if user_id: parent_span.set_attribute("user.id", str(user_id))
            if mr_id: parent_span.set_attribute("mr.id", str(mr_id))
            if repository_id: parent_span.set_attribute("repository.id", str(repository_id))
            parent_span.set_attribute("operation.type", "review")

            print(f"[INFO] Initializing GitNexus MCP integration...")

            # Save current directory and change to repo directory
            # GitNexus MCP needs to run from within the repository
            original_cwd = os.getcwd()
            repo_dir = str(repo_path)
            os.chdir(repo_dir)
            print(f"[INFO] Changed working directory to: {repo_dir}")

            mcp_directory_restored = False

            try:
                # 1. Spawning GitNexus Subprocess Context via Stdio Transport
                # GitNexus needs to be run with the 'mcp' subcommand
                server_params = StdioServerParameters(
                    command="gitnexus",
                    args=["mcp"],
                    env={**os.environ}
                )

                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as mcp_session:
                        await mcp_session.initialize()

                        # 2. Extract tools manifest from GitNexus
                        gitnexus_manifest = await mcp_session.list_tools()
                        print(f"[INFO] GitNexus tools available: {len(gitnexus_manifest.tools)}")

                        # 3. Convert to Gemini's Function Declarations format
                        gemini_tools = [convert_mcp_tools_to_gemini(gitnexus_manifest.tools)]

                        # 4. Construct Agent Conversation History
                        history = [
                            types.Content(role="user", parts=[types.Part.from_text(text=review_prompt)])
                        ]

                        # 5. Continuous Agent Iteration Loop
                        max_iterations = 15
                        iteration = 0

                        while iteration < max_iterations:
                            iteration += 1

                            response = await call_gemini_with_retry(
                                client.models.generate_content,
                                model=model,
                                contents=history,
                                config=types.GenerateContentConfig(
                                    system_instruction=system_instruction,
                                    tools=gemini_tools,
                                    temperature=0.1
                                )
                            )

                            # Parse and accumulate usage metrics
                            usage_metadata = getattr(response, 'usage_metadata', None)
                            if usage_metadata:
                                total_input_tokens += getattr(usage_metadata, 'prompt_token_count', 0)
                                total_output_tokens += getattr(usage_metadata, 'candidates_token_count', 0)

                            # Record model output
                            model_content = response.candidates[0].content
                            history.append(model_content)

                            # Capture current span context
                            current_span = trace.get_current_span()
                            if current_span and current_span.is_recording():
                                span_context = current_span.get_span_context()
                                llm_span_id = format(span_context.span_id, 'x')

                                if user_id: current_span.set_attribute("user.id", str(user_id))
                                if mr_id: current_span.set_attribute("mr.id", str(mr_id))
                                if repository_id: current_span.set_attribute("repository.id", str(repository_id))
                                current_span.set_attribute("operation.type", "review")

                            # Check for function call - iterate through all parts
                            func_call = None
                            for part in model_content.parts:
                                if hasattr(part, 'function_call') and part.function_call:
                                    func_call = part.function_call
                                    break

                            if func_call:
                                print(f"[INFO] Gemini calling GitNexus tool: {func_call.name}")

                                tools_called.append(func_call.name)

                                # Inject repo parameter automatically - don't let Gemini choose
                                tool_args = dict(func_call.args)
                                if repo_name:
                                    # Tools that support repo parameter
                                    repo_supported_tools = {
                                        'impact', 'context', 'query', 'detect_changes',
                                        'cypher', 'route_map', 'tool_map', 'shape_check', 'api_impact'
                                    }
                                    if func_call.name in repo_supported_tools:
                                        tool_args['repo'] = repo_name
                                        print(f"[INFO] Auto-injected repo='{repo_name}' into {func_call.name} call")
                                elif func_call.name in repo_supported_tools:
                                    print(f"[WARN] GitNexus tool {func_call.name} needs repo but none provided!")

                                # Execute via MCP
                                try:
                                    mcp_output = await asyncio.wait_for(
                                        mcp_session.call_tool(
                                            name=func_call.name,
                                            arguments=tool_args
                                        ),
                                        timeout=MCP_TIMEOUT
                                    )

                                    # Extract text from result
                                    tool_result_text = "".join([
                                        block.text for block in mcp_output.content
                                        if hasattr(block, 'text')
                                    ])

                                    print(f"[INFO] Tool result: {len(tool_result_text)} chars")

                                    # Feed back to Gemini
                                    tool_response = types.Content(
                                        role="tool",
                                        parts=[types.Part.from_function_response(
                                            name=func_call.name,
                                            response={"result": tool_result_text}
                                        )]
                                    )
                                    history.append(tool_response)

                                except asyncio.TimeoutError:
                                    error_msg = f"Tool call timed out after {MCP_TIMEOUT}s"
                                    print(f"[WARN] {error_msg}")
                                    history.append(types.Content(
                                        role="tool",
                                        parts=[types.Part.from_function_response(
                                            name=func_call.name,
                                            response={"error": error_msg}
                                        )]
                                    ))
                                    # Continue to final response
                                    try:
                                        review_text = response.text
                                    except:
                                        review_text = "Error: Tool timeout during review"
                                    break
                                except Exception as e:
                                    error_msg = f"Tool call failed: {str(e)}"
                                    print(f"[WARN] {error_msg}")
                                    history.append(types.Content(
                                        role="tool",
                                        parts=[types.Part.from_function_response(
                                            name=func_call.name,
                                            response={"error": error_msg}
                                        )]
                                    ))
                                    # Continue to final response
                                    try:
                                        review_text = response.text
                                    except:
                                        review_text = f"Error: {error_msg}"
                                    break
                            else:
                                # No more tool calls - get final response
                                try:
                                    review_text = response.text
                                except Exception as text_err:
                                    print(f"[ERROR] Error accessing final response.text: {text_err}")
                                    review_text = "Error: Could not extract final review text"
                                break

                        if iteration >= max_iterations:
                            print(f"[WARN] Reached max iterations ({max_iterations})")

                # Restore original working directory after MCP operations complete
                os.chdir(original_cwd)
                mcp_directory_restored = True
                print(f"[INFO] Restored working directory to: {original_cwd}")

            finally:
                # Ensure directory is restored even if an error occurred
                if not mcp_directory_restored:
                    try:
                        os.chdir(original_cwd)
                        print(f"[INFO] Restored working directory in finally block: {original_cwd}")
                    except Exception as restore_err:
                        print(f"[ERROR] Failed to restore working directory: {restore_err}")

            # Capture trace_id while span context is still attached
            from ai_observability.trace_utils import get_current_trace_id
            current_trace_id = get_current_trace_id()
            if current_trace_id:
                print(f"[INFO] Captured trace_id for MR {mr_id}: {current_trace_id[:16]}...")
            else:
                print(f"[WARN] No active trace found during review")

    except Exception as e:
        print(f"[ERROR] GitNexus integration failed: {e}")
        import traceback
        traceback.print_exc()

        # Fallback to basic review without tools
        print(f"[INFO] Falling back to basic review without GitNexus tools")
        try:
            response = await call_gemini_with_retry(
                client.models.generate_content,
                model=model,
                contents=review_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1
                )
            )

            usage_metadata = getattr(response, 'usage_metadata', None)
            if usage_metadata:
                total_input_tokens = getattr(usage_metadata, 'prompt_token_count', 0)
                total_output_tokens = getattr(usage_metadata, 'candidates_token_count', 0)

            review_text = response.text
        except Exception as fallback_err:
            print(f"[ERROR] Fallback review also failed: {fallback_err}")
            review_text = f"Error: Review failed - {str(e)}"

    finally:
        context.detach(token)

    # 6. Map Total Unified Metrics
    usage_data = {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "model_name": model
    }

    # Track overall usage directly to MongoDB
    if user_id and usage_data.get("total_tokens", 0) > 0:
        await track_llm_usage(
            user_id=user_id,
            model_name=model,
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            operation_type="review",
            mr_id=mr_id,
            repository_id=repository_id,
            trace_id=current_trace_id
        )

    return {
        "review_text": review_text,
        "usage": usage_data,
        "trace_id": current_trace_id,
        "span_id": llm_span_id,
        "tools_called": tools_called
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
            llm_span_id = None  # Capture the LLM span ID for annotations
            if current_span and current_span.is_recording():
                span_context = current_span.get_span_context()
                llm_span_id = format(span_context.span_id, 'x')  # Capture span ID as hex string
                print(f"[INFO] Post-LLM current span: {llm_span_id}...")

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
    try:
        usage_metadata = getattr(fix_analysis, 'usage_metadata', None)

        usage_data = {
            "input_tokens": getattr(usage_metadata, 'prompt_token_count', 0) if usage_metadata else 0,
            "output_tokens": getattr(usage_metadata, 'candidates_token_count', 0) if usage_metadata else 0,
            "total_tokens": getattr(usage_metadata, 'total_token_count', 0) if usage_metadata else 0,
            "model_name": model
        }
    except Exception as metadata_err:
        print(f"[ERROR] Error extracting usage metadata: {metadata_err}")
        import traceback
        traceback.print_exc()
        usage_data = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model_name": model}

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

    try:
        response_text = fix_analysis.text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        # Parse JSON and add usage data
        fix_result = json.loads(response_text)
        fix_result["usage"] = usage_data
        fix_result["span_id"] = llm_span_id  # Include LLM span ID for Arize annotations

        return fix_result
    except Exception as parse_err:
        print(f"[ERROR] Error parsing fix analysis response: {parse_err}")
        import traceback
        traceback.print_exc()
        # Return a safe default if parsing fails
        return {
            "fixable": False,
            "fixes": [],
            "usage": usage_data,
            "error": str(parse_err)
        }
