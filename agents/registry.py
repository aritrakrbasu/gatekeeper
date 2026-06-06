from typing import Dict, Any, List, Optional
from agents.base_tool import BaseTool, LocalTool
from agents.context import AgentContext
from agents.mcp_wrappers import GitLabMCPTool, MongoMCPTool, DynatraceMCPTool, GitNexusMCPTool, SentryMCPTool


class ToolRegistry:
    """
    Unified Tool Registry managing BaseTool instances for both local Python callbacks
    and remote stdio MCP ClientSessions.
    """

    def __init__(self):
        # Map of tool_name -> BaseTool instance
        self._tools: Dict[str, BaseTool] = {}

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
                    "parameters": tool.inputSchema
                }
                
                # Instantiate respective wrapper
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
                    # Fallback to base wrapper
                    from agents.mcp_wrappers import BaseMCPTool
                    wrapper = BaseMCPTool(
                        name=tool.name,
                        description=tool.description,
                        schema=schema,
                        session_name=session_name,
                        session_getter=lambda: mcp_session
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

    async def execute_tool(self, name: str, arguments: Dict[str, Any], context: Optional[AgentContext] = None) -> Any:
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
                schema_ctx=schema
            )
            
        tool = self.get_tool(name)
        result = await tool.execute(arguments, context)
        if result.status == "error":
            raise RuntimeError(result.error_message)
        return result.content


async def build_default_registry() -> ToolRegistry:
    """
    Creates and populates a ToolRegistry with all active local services and MCP servers.
    """
    from services import mcp_service
    from agents import tools

    registry = ToolRegistry()

    # 1. Register local Python tools
    registry.register_local_tool("clone_repo", tools.clone_repo_schema, tools.clone_repo)
    registry.register_local_tool("run_impact_analysis", tools.run_impact_analysis_schema, tools.run_impact_analysis)
    registry.register_local_tool("run_schema_inspection", tools.run_schema_inspection_schema, tools.run_schema_inspection)
    registry.register_local_tool("get_gitlab_mr_diffs", tools.get_gitlab_mr_diffs_schema, tools.get_gitlab_mr_diffs)
    registry.register_local_tool("post_gitlab_mr_comment", tools.post_gitlab_mr_comment_schema, tools.post_gitlab_mr_comment)
    registry.register_local_tool("get_dynatrace_incident_details", tools.get_dynatrace_incident_details_schema, tools.get_dynatrace_incident_details)
    registry.register_local_tool("apply_hotfix_patch", tools.apply_hotfix_patch_schema, tools.apply_hotfix_patch)
    registry.register_local_tool("create_hotfix_branch_and_mr", tools.create_hotfix_branch_and_mr_schema, tools.create_hotfix_branch_and_mr)
    registry.register_local_tool("gitnexus_analyze", tools.gitnexus_analyze_schema, tools.gitnexus_analyze)

    # GitLab REST API tools (direct API calls without MCP)
    registry.register_local_tool("create_gitlab_branch", tools.create_gitlab_branch_schema, tools.create_gitlab_branch)
    registry.register_local_tool("create_gitlab_merge_request", tools.create_gitlab_merge_request_schema, tools.create_gitlab_merge_request)
    registry.register_local_tool("commit_file_to_branch", tools.commit_file_to_branch_schema, tools.commit_file_to_branch)

    # 2. Register active Stdio MCP sessions dynamically if they are initialized
    if mcp_service.gitlab_session:
        await registry.register_mcp_session("gitlab", mcp_service.gitlab_session)
    if mcp_service.mongo_session:
        await registry.register_mcp_session("mongodb", mcp_service.mongo_session)
    if mcp_service.nexus_session:
        await registry.register_mcp_session("gitnexus", mcp_service.nexus_session)
    if mcp_service.dynatrace_session:
        await registry.register_mcp_session("dynatrace", mcp_service.dynatrace_session)
    if mcp_service.sentry_session:
        await registry.register_mcp_session("sentry", mcp_service.sentry_session)

    return registry
