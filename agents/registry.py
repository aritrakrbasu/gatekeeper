import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from agents.base_tool import BaseTool, LocalTool
from agents.context import AgentContext
from agents.mcp_wrappers import GitLabMCPTool, MongoMCPTool, DynatraceMCPTool, GitNexusMCPTool, SentryMCPTool
from peil.capture.sanitize import mask_sensitive_arguments
from peil.models.enums import CaptureEventType

if TYPE_CHECKING:
    from agents.aril_bridge import ArilSession


class ToolRegistry:
    """
    Unified Tool Registry managing BaseTool instances for both local Python callbacks
    and remote stdio MCP ClientSessions.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._aril: Optional["ArilSession"] = None

    def attach_aril(self, aril: Optional["ArilSession"]) -> None:
        """Attach ARIL session for tool lifecycle capture."""
        self._aril = aril

    def register_tool(self, tool: BaseTool) -> None:
        """Registers a formal BaseTool instance."""
        name = tool.get_name()
        self._tools[name] = tool
        print(f"[OK] [ToolRegistry] Registered tool: '{name}' (Type: {type(tool).__name__})")

    def register_local_tool(self, name: str, schema: Dict[str, Any], callback: Any) -> None:
        """Registers a native python callback wrapped in a LocalTool."""
        local_tool = LocalTool(name=name, description=schema.get("description", ""), schema=schema, callback=callback)
        self.register_tool(local_tool)

    async def register_mcp_session(self, session_name: str, mcp_session: Any) -> None:
        """
        Queries all capabilities of a remote MCP session and registers them
        as respective MCP tool wrappers.
        """
        if not mcp_session:
            return

        try:
            tools_resp = await mcp_session.list_tools()
            registered_count = 0
            for tool in tools_resp.tools:
                schema = {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }

                if session_name == "gitlab":
                    wrapper = GitLabMCPTool(name=tool.name, description=tool.description, schema=schema)
                elif session_name == "mongodb":
                    wrapper = MongoMCPTool(name=tool.name, description=tool.description, schema=schema)
                elif session_name == "dynatrace":
                    wrapper = DynatraceMCPTool(name=tool.name, description=tool.description, schema=schema)
                elif session_name == "gitnexus":
                    wrapper = GitNexusMCPTool(name=tool.name, description=tool.description, schema=schema)
                elif session_name == "sentry":
                    wrapper = SentryMCPTool(name=tool.name, description=tool.description, schema=schema)
                else:
                    from agents.mcp_wrappers import BaseMCPTool
                    wrapper = BaseMCPTool(
                        name=tool.name,
                        description=tool.description,
                        schema=schema,
                        session_name=session_name,
                        session_getter=lambda: mcp_session,
                    )

                self.register_tool(wrapper)
                registered_count += 1
            print(f"[OK] [ToolRegistry] Registered {registered_count} tools from MCP session '{session_name}'")
        except Exception as e:
            print(f"[WARN] [ToolRegistry] Failed to register tools from MCP session '{session_name}': {e}")

    def get_tool(self, name: str) -> BaseTool:
        """Retrieves a registered tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered in ToolRegistry")
        return self._tools[name]

    def list_tools(self) -> List[BaseTool]:
        """Lists all registered tools."""
        return list(self._tools.values())

    def get_gemini_tools(self) -> List[Any]:
        """Backwards compatibility helper that delegates to GeminiToolAdapter."""
        from agents.adapter import GeminiToolAdapter
        adapter = GeminiToolAdapter(self)
        return adapter.get_gemini_tools()

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Optional[AgentContext] = None,
        step_id: Optional[str] = None,
    ) -> Any:
        """
        Resolves, validates, and executes the specified tool.
        Returns the output from the tool execution (normalizing errors).
        """
        if context is None:
            from agents.context import RepositoryContext, BranchContext, UserContext, SchemaContext, AgentContext
            repo = RepositoryContext(id="dummy-repo", name="dummy-repo")
            branch = BranchContext(source_branch="main", target_branch="main")
            user = UserContext(user_id="dummy-user", username="dummy")
            schema = SchemaContext()
            context = AgentContext(
                task_id="dummy-task",
                objective="dummy",
                repository=repo,
                branch=branch,
                user=user,
                schema_ctx=schema,
            )

        masked_args = mask_sensitive_arguments(arguments)
        aril = self._aril
        if aril is not None:
            try:
                aril.emit(
                    CaptureEventType.TOOL_INVOKED,
                    {
                        "tool_name": name,
                        "masked_arguments": masked_args,
                        "step_id": step_id,
                    },
                )
            except Exception as exc:
                print(f"[WARN] [ToolRegistry] ARIL tool_invoked emit failed: {exc}")

        start = time.time()
        tool = self.get_tool(name)
        result = await tool.execute(arguments, context)
        duration_ms = (time.time() - start) * 1000.0

        result_ref: Optional[str] = None
        if aril is not None:
            try:
                from agents.aril_bridge import serialize_for_evidence

                if result.content is not None:
                    result_ref = await aril.evidence_repo.store(
                        execution_id=aril.execution_id,
                        payload=serialize_for_evidence(result.content),
                        content_type="application/json",
                    )
                status = "success" if result.status != "error" else "error"
                aril.emit(
                    CaptureEventType.TOOL_COMPLETED,
                    {
                        "tool_name": name,
                        "result_ref": result_ref,
                        "duration_ms": duration_ms,
                        "status": status,
                        "step_id": step_id,
                        "error_message": result.error_message,
                    },
                )
                await aril.flush()
            except Exception as exc:
                print(f"[WARN] [ToolRegistry] ARIL tool_completed emit failed: {exc}")

        if result.status == "error":
            raise RuntimeError(result.error_message)
        return result.content


async def build_default_registry(aril: Optional["ArilSession"] = None, exclude_prerequisites: bool = False) -> ToolRegistry:
    """
    Creates and populates a ToolRegistry with all active local services and MCP servers.

    Args:
        aril: Optional ARIL session for tool lifecycle capture
        exclude_prerequisites: If True, excludes prerequisite tools that are executed
                               before LLM planning (validate_mr_webhook, clone_repo,
                               gitnexus_analyze, get_gitlab_mr_diffs)
    """
    from services import mcp_service
    from agents import tools

    # Prerequisite tools that are executed before LLM planning
    PREREQUISITE_TOOLS = {
        "validate_mr_webhook",
        "clone_repo",
        "gitnexus_analyze",
        "get_gitlab_mr_diffs",
    }

    print(f"[DEBUG] [build_default_registry] Starting to build registry (exclude_prerequisites={exclude_prerequisites})...")
    registry = ToolRegistry()
    if aril is not None:
        registry.attach_aril(aril)

    print(f"[DEBUG] [build_default_registry] Registering local tools...")

    # Core local tools
    local_tools_to_register = [
        ("run_impact_analysis", tools.run_impact_analysis_schema, tools.run_impact_analysis),
        ("run_schema_inspection", tools.run_schema_inspection_schema, tools.run_schema_inspection),
        ("run_gemini_mr_review", tools.run_gemini_mr_review_schema, tools.run_gemini_mr_review),
        ("post_gitlab_mr_comment", tools.post_gitlab_mr_comment_schema, tools.post_gitlab_mr_comment),
        ("get_dynatrace_incident_details", tools.get_dynatrace_incident_details_schema, tools.get_dynatrace_incident_details),
        ("apply_hotfix_patch", tools.apply_hotfix_patch_schema, tools.apply_hotfix_patch),
        ("create_hotfix_branch_and_mr", tools.create_hotfix_branch_and_mr_schema, tools.create_hotfix_branch_and_mr),
    ]

    # Add prerequisite tools only if not excluding them
    if not exclude_prerequisites:
        local_tools_to_register.extend([
            ("clone_repo", tools.clone_repo_schema, tools.clone_repo),
            ("get_gitlab_mr_diffs", tools.get_gitlab_mr_diffs_schema, tools.get_gitlab_mr_diffs),
            ("gitnexus_analyze", tools.gitnexus_analyze_schema, tools.gitnexus_analyze),
            ("validate_mr_webhook", tools.validate_mr_webhook_schema, tools.validate_mr_webhook),
        ])
        print(f"[DEBUG] [build_default_registry] Including prerequisite tools")
    else:
        print(f"[DEBUG] [build_default_registry] Excluding prerequisite tools: {PREREQUISITE_TOOLS}")

    # Register all local tools
    for tool_name, schema, callback in local_tools_to_register:
        registry.register_local_tool(tool_name, schema, callback)

    # GitLab REST API tools (direct API calls without MCP)
    registry.register_local_tool("create_gitlab_branch", tools.create_gitlab_branch_schema, tools.create_gitlab_branch)
    registry.register_local_tool("create_gitlab_merge_request", tools.create_gitlab_merge_request_schema, tools.create_gitlab_merge_request)
    registry.register_local_tool("commit_file_to_branch", tools.commit_file_to_branch_schema, tools.commit_file_to_branch)

    # GitNexus tools (for code search and file reading)
    registry.register_local_tool("gitnexus_grep", tools.gitnexus_grep_schema, tools.gitnexus_grep)
    registry.register_local_tool("gitnexus_file", tools.gitnexus_file_schema, tools.gitnexus_file)

    # AI Fix Generation Tool
    registry.register_local_tool("generate_fix", tools.generate_fix_schema, tools.generate_fix)

    # MR Review Enhancement Tools (feature parity with standard mode)
    registry.register_local_tool("post_loading_indicator", tools.post_loading_indicator_schema, tools.post_loading_indicator)
    registry.register_local_tool("update_review_comment", tools.update_review_comment_schema, tools.update_review_comment)
    registry.register_local_tool("update_commit_status", tools.update_commit_status_schema, tools.update_commit_status)
    registry.register_local_tool("track_progress", tools.track_progress_schema, tools.track_progress)

    print(f"[DEBUG] [build_default_registry] Starting MCP session registrations...")
    print(f"[DEBUG] [build_default_registry] GitLab session: {mcp_service.gitlab_session is not None}")
    print(f"[DEBUG] [build_default_registry] Mongo session: {mcp_service.mongo_session is not None}")
    print(f"[DEBUG] [build_default_registry] Nexus session: {mcp_service.nexus_session is not None}")
    print(f"[DEBUG] [build_default_registry] Dynatrace session: {mcp_service.dynatrace_session is not None}")
    print(f"[DEBUG] [build_default_registry] Sentry session: {mcp_service.sentry_session is not None}")

    if mcp_service.gitlab_session:
        print(f"[DEBUG] [build_default_registry] Registering GitLab MCP session...")
        await registry.register_mcp_session("gitlab", mcp_service.gitlab_session)
    if mcp_service.mongo_session:
        print(f"[DEBUG] [build_default_registry] Registering MongoDB MCP session...")
        await registry.register_mcp_session("mongodb", mcp_service.mongo_session)
    if mcp_service.nexus_session:
        print(f"[DEBUG] [build_default_registry] Registering GitNexus MCP session...")
        await registry.register_mcp_session("gitnexus", mcp_service.nexus_session)
    if mcp_service.dynatrace_session:
        print(f"[DEBUG] [build_default_registry] Registering Dynatrace MCP session...")
        await registry.register_mcp_session("dynatrace", mcp_service.dynatrace_session)
    if mcp_service.sentry_session:
        print(f"[DEBUG] [build_default_registry] Registering Sentry MCP session...")
        await registry.register_mcp_session("sentry", mcp_service.sentry_session)

    print(f"[DEBUG] [build_default_registry] Registry build complete. Total tools: {len(registry._tools)}")
    return registry
