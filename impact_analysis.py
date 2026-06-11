"""
Impact Analysis Module for Code Change Review

This module provides impact analysis capabilities by integrating GitNexus MCP tools
directly with Gemini. Instead of performing manual analysis, it passes GitNexus tools
to Gemini so that Gemini can call them dynamically when needed for context.

Integrates with GitNexus (https://github.com/abhigyanpatwari/GitNexus) for advanced
code intelligence via MCP.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Timeout for MCP tool calls (in seconds)
MCP_TIMEOUT = 30


@dataclass
class ImpactAnalysisResult:
    """Result from Gemini-powered impact analysis."""
    analysis_text: str
    usage: Dict[str, any]
    trace_id: Optional[str] = None
    tools_called: List[str] = field(default_factory=list)


class GitNexusGeminiIntegration:
    """
    Integrates GitNexus MCP tools with Gemini for dynamic impact analysis.

    This approach lets Gemini decide when and how to use GitNexus tools,
    rather than pre-computing impact analysis.
    """

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize the integration.

        Args:
            repo_path: Path to the git repository. If None, uses current directory.
        """
        self.repo_path = repo_path or Path.cwd()

    async def analyze_with_gemini(
        self,
        diff_content: str,
        changed_files: List[str],
        client: genai.Client,
        model: str = 'gemini-2.5-pro',
        system_instruction: Optional[str] = None
    ) -> ImpactAnalysisResult:
        """
        Run impact analysis by giving Gemini access to GitNexus tools.

        Args:
            diff_content: The diff content to analyze
            changed_files: List of changed file paths
            client: Gemini client
            model: Model name to use
            system_instruction: Optional system instruction for Gemini

        Returns:
            ImpactAnalysisResult with analysis text and usage metrics
        """
        if system_instruction is None:
            system_instruction = await self._default_system_instruction()

        # Build the analysis prompt
        analysis_prompt = await self._build_analysis_prompt(diff_content, changed_files)

        # Track tools that were called
        tools_called = []

        try:
            # Save current directory and change to repo directory
            # GitNexus MCP needs to run from within the repository
            original_cwd = os.getcwd()
            repo_dir = str(self.repo_path)
            os.chdir(repo_dir)
            print(f"[INFO] Changed working directory to: {repo_dir}")

            mcp_directory_restored = False

            try:
                # 1. Spawn GitNexus subprocess via stdio transport
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

                        # 3. Map to Gemini's Function Declarations format
                        gemini_tools = self._convert_to_gemini_tools(gitnexus_manifest.tools)

                        print(f"[INFO] GitNexus MCP tools available: {len(gemini_tools[0].function_declarations)}")

                        # 4. Build conversation history
                        history = [
                            types.Content(role="user", parts=[types.Part.from_text(text=analysis_prompt)])
                        ]

                        total_input_tokens = 0
                        total_output_tokens = 0
                        analysis_text = ""

                        # 5. Continuous iteration loop for tool calls
                        max_iterations = 10  # Prevent infinite loops
                        iteration = 0

                        while iteration < max_iterations:
                            iteration += 1

                            # Call Gemini with tools
                            response = await asyncio.to_thread(
                                client.models.generate_content,
                                model=model,
                                contents=history,
                                config=types.GenerateContentConfig(
                                    system_instruction=system_instruction,
                                    tools=gemini_tools,
                                    temperature=0.2
                                )
                            )

                            # Accumulate usage metrics
                            usage_metadata = getattr(response, 'usage_metadata', None)
                            if usage_metadata:
                                total_input_tokens += getattr(usage_metadata, 'prompt_token_count', 0)
                                total_output_tokens += getattr(usage_metadata, 'candidates_token_count', 0)

                            # Get model output
                            model_content = response.candidates[0].content
                            history.append(model_content)

                            # Check for function call - iterate through all parts
                            func_call = None
                            for part in model_content.parts:
                                if hasattr(part, 'function_call') and part.function_call:
                                    func_call = part.function_call
                                    break

                            if func_call:
                                print(f"[INFO] Gemini calling GitNexus tool: {func_call.name}")

                                tools_called.append(func_call.name)

                                # Execute via MCP
                                try:
                                    mcp_output = await asyncio.wait_for(
                                        mcp_session.call_tool(
                                            name=func_call.name,
                                            arguments=dict(func_call.args)
                                        ),
                                        timeout=MCP_TIMEOUT
                                    )

                                    # Extract text from result
                                    tool_result_text = "".join([
                                        block.text for block in mcp_output.content
                                        if hasattr(block, 'text')
                                    ])

                                    print(f"[INFO] Tool result length: {len(tool_result_text)} chars")

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
                                    break
                            else:
                                # No more tool calls - get final response
                                try:
                                    analysis_text = response.text
                                except Exception:
                                    analysis_text = "Error: Could not extract analysis text"
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

        except Exception as e:
            print(f"[ERROR] GitNexus integration failed: {e}")
            # Fallback to basic analysis without tools
            analysis_text = await self._fallback_analysis(diff_content, changed_files)
            total_input_tokens = 0
            total_output_tokens = 0

        return ImpactAnalysisResult(
            analysis_text=analysis_text,
            usage={
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "model_name": model
            },
            tools_called=tools_called
        )

    async def _default_system_instruction(self) -> str:
        """Default system instruction for impact analysis."""
        try:
            from config.prompts import load_impact_analysis_system
            return await load_impact_analysis_system(label="production")
        except Exception as e:
            print(f"[WARN] Failed to load impact_analysis_system from Arize AX: {e}, using fallback")
            return """You are a senior code reviewer specializing in impact analysis.

Your task is to analyze code changes and identify:
1. Breaking changes that could affect other parts of the codebase
2. Critical dependencies and call chains
3. Potential ripple effects beyond the directly changed files
4. Security implications of the changes

You have access to GitNexus tools that can help you understand:
- Impact scope of specific symbols (impact tool)
- Changed symbols and affected processes (detect_changes tool)
- 360-degree context for symbols (context tool)
- Process-grouped search (query tool)

Use these tools strategically when you need more context about:
- What depends on the changed code
- What the changed code depends on
- Related functions and processes
- Usage patterns across the codebase

Provide a clear, structured analysis with severity levels (CRITICAL, HIGH, MEDIUM, LOW)."""

    async def _build_analysis_prompt(self, diff_content: str, changed_files: List[str]) -> str:
        """Build the analysis prompt for Gemini."""
        try:
            from config.prompts import load_and_format_prompt
            changed_files_str = chr(10).join(f"- {f}" for f in changed_files)
            return await load_and_format_prompt(
                "impact_analysis_template",
                diff_content=diff_content,
                changed_files=changed_files_str
            )
        except Exception as e:
            print(f"[WARN] Failed to load impact_analysis_template from Arize AX: {e}, using fallback")
            return f"""Analyze this code change for impact and potential issues:

## Changed Files
{chr(10).join(f"- {f}" for f in changed_files)}

## Diff Content
{diff_content}

Use the available GitNexus tools to:
1. Identify what depends on the changed functions/classes
2. Find call chains that might be affected
3. Detect any breaking API changes
4. Understand the broader context of the changes

Provide your analysis with clear severity levels and actionable recommendations."""

    def _convert_to_gemini_tools(self, mcp_tools) -> List[types.Tool]:
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
                param_properties[prop_name] = self._convert_mcp_property_to_gemini(prop_def)

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

        return [types.Tool(function_declarations=function_declarations)]

    def _convert_mcp_property_to_gemini(self, prop_def: dict) -> types.Schema:
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
                items=self._convert_mcp_property_to_gemini(items_def)
            )

        # Handle Objects
        if prop_type == 'OBJECT':
            nested_properties = prop_def.get('properties', {})
            nested_required = prop_def.get('required', [])

            mapped_nested = {
                k: self._convert_mcp_property_to_gemini(v)
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

    def _map_json_type_to_gemini(self, json_type: str) -> str:
        """Map JSON Schema types to Gemini types. (Deprecated - use _convert_mcp_property_to_gemini)"""
        type_map = {
            "string": "string",
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
            "array": "array",
            "object": "object"
        }
        return type_map.get(json_type, "string")

    async def _fallback_analysis(self, diff_content: str, changed_files: List[str]) -> str:
        """
        Fallback analysis when GitNexus is not available.

        Provides basic pattern-based analysis.
        """
        import re

        findings = []

        # Check for API changes
        api_patterns = [
            r'@\.(route|get|post|put|delete|patch)\(',
            r'@api\.',
            r'@.*\.(get|post|put|delete|patch)\('
        ]

        for pattern in api_patterns:
            if re.search(pattern, diff_content):
                findings.append("🔴 **HIGH**: API route changes detected - may affect consumers")
                break

        # Check for config changes
        config_files = [f for f in changed_files if any(
            x in f.lower() for x in ['config', 'setting', 'env', 'docker', 'package']
        )]
        if config_files:
            findings.append(f"🟠 **HIGH**: Configuration files changed: {', '.join(config_files)}")

        # Check for test changes
        test_files = [f for f in changed_files if 'test' in f.lower()]
        if test_files:
            findings.append(f"ℹ️ **INFO**: Test files modified: {', '.join(test_files)}")

        # Check for function changes
        func_pattern = r'(def |async def |function |const |let )[\w_]+\('
        if re.search(func_pattern, diff_content):
            findings.append("🟡 **MEDIUM**: Function/method signatures changed - check call sites")

        if not findings:
            findings.append("ℹ️ **INFO**: No obvious impact patterns detected")

        return "## Impact Analysis (Fallback - GitNexus unavailable)\n\n" + "\n".join(f"- {f}" for f in findings)


async def run_impact_analysis(
    diff_content: str,
    changed_files: List[str],
    client: genai.Client = None,
    model: str = 'gemini-2.5-pro',
    repo_path: Optional[Path] = None
) -> ImpactAnalysisResult:
    """
    Main entry point for running impact analysis with GitNexus + Gemini.

    Args:
        diff_content: The code diff to analyze
        changed_files: List of changed file paths
        client: Optional Gemini client (uses default if None)
        model: Model name to use
        repo_path: Optional repository path

    Returns:
        ImpactAnalysisResult with analysis and usage data
    """
    # Import default client if none provided
    if client is None:
        from services.gemini_service import ai_client
        client = ai_client

    integration = GitNexusGeminiIntegration(repo_path=repo_path)

    result = await integration.analyze_with_gemini(
        diff_content=diff_content,
        changed_files=changed_files,
        client=client,
        model=model
    )

    return result


# Legacy compatibility - keep old interface for existing code
async def run_pre_review_analysis(
    project_id: str,
    mr_iid: int,
    source_branch: str,
    target_branch: str,
    changed_files: List[str],
    gitlab_session,
    nexus_session=None
) -> Tuple:
    """
    Legacy interface - redirects to new Gemini-powered analysis.

    This maintains backward compatibility while using the new approach.
    """
    # For now, return a simple formatted context
    # The actual analysis will be done by Gemini with tools

    context = f"""
## Impact Analysis Context

- **Project ID**: {project_id}
- **MR IID**: {mr_iid}
- **Branch**: {source_branch} → {target_branch}
- **Changed Files**: {len(changed_files)}

### Files Changed
{chr(10).join(f"- {f}" for f in changed_files[:20])}

*Impact analysis will be performed dynamically by Gemini using GitNexus tools during review.*
"""

    # Return a simple report object and context
    class SimpleReport:
        def __init__(self):
            self.changed_files = set(changed_files)
            self.analyzed_files = set()
            self.findings = []
            self.execution_time_seconds = 0.0
            self.project_id = project_id
            self.merge_request_iid = mr_iid
            self.source_branch = source_branch
            self.target_branch = target_branch

    return SimpleReport(), context
