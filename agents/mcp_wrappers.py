import asyncio
import time
import logging
from typing import Dict, Any, Optional, Callable
from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.observability import ToolExecutionEvent, record_tool_event
from services import mcp_service

logger = logging.getLogger(__name__)


class BaseMCPTool(BaseTool):
    """
    Subclass interface that coordinates tool executions with remote stdio MCP ClientSessions.
    Provides execution retries, timeouts, and structured logs.
    """
    def __init__(
        self,
        name: str,
        description: str,
        schema: Dict[str, Any],
        session_name: str,
        session_getter: Callable[[], Any],
        timeout_seconds: int = 30,
        max_retries: int = 3
    ):
        self.name = name
        self.description = description
        self.schema = schema
        self.session_name = session_name
        self.session_getter = session_getter
        self.timeout = timeout_seconds
        self.max_retries = max_retries

    def get_name(self) -> str:
        return self.name

    def get_description(self) -> str:
        return self.description

    def get_schema(self) -> Dict[str, Any]:
        return self.schema

    def validate(self, arguments: Dict[str, Any]) -> None:
        params = self.schema.get("parameters", {})
        required = params.get("required", [])
        for req in required:
            if req not in arguments:
                raise ValueError(f"Missing required parameter: '{req}'")
        
        properties = params.get("properties", {})
        for key, value in arguments.items():
            if key not in properties:
                continue
            prop_type = str(properties[key].get("type", "")).upper()
            if prop_type == "STRING" and not isinstance(value, str):
                raise TypeError(f"Parameter '{key}' must be a string")
            elif prop_type == "INTEGER" and not isinstance(value, int) and not (isinstance(value, float) and value.is_integer()):
                raise TypeError(f"Parameter '{key}' must be an integer")
            elif prop_type == "BOOLEAN" and not isinstance(value, bool):
                raise TypeError(f"Parameter '{key}' must be a boolean")

    async def execute(self, arguments: Dict[str, Any], context: AgentContext) -> ToolResult:
        try:
            self.validate(arguments)
        except Exception as ve:
            return ToolResult(
                status="error",
                content=None,
                error_message=f"Validation failed: {ve}",
                execution_time_ms=0.0,
                retry_count=0
            )
            
        session = self.session_getter()
        if not session:
            err_msg = f"Active session for {self.session_name} is not initialized/available"
            return ToolResult(
                status="error",
                content=None,
                error_message=err_msg,
                execution_time_ms=0.0,
                retry_count=0
            )

        start_time = time.time()
        retries = 0
        backoff = 1.0
        last_err = None
        
        while retries <= self.max_retries:
            try:
                print(f"[INFO] [MCPToolWrapper:{self.name}] Invoking... (Attempt {retries + 1}/{self.max_retries + 1})")
                
                # Subprocess call wrapping with timeout
                result = await asyncio.wait_for(
                    session.call_tool(name=self.name, arguments=arguments),
                    timeout=self.timeout
                )
                
                duration_ms = (time.time() - start_time) * 1000.0
                
                # Normalize output
                normalized_content = ""
                if hasattr(result, "content") and result.content:
                    normalized_content = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
                else:
                    normalized_content = str(result)
                    
                try:
                    import json
                    normalized_content = json.loads(normalized_content)
                except:
                    pass

                # Record event using observability
                event = ToolExecutionEvent(
                    tool_name=self.name,
                    arguments=arguments,
                    status="success",
                    duration_ms=duration_ms,
                    retry_count=retries
                )
                await record_tool_event(event)

                return ToolResult(
                    status="success",
                    content=normalized_content,
                    execution_time_ms=duration_ms,
                    retry_count=retries
                )
                
            except Exception as e:
                last_err = e
                print(f"[WARN] [MCPToolWrapper:{self.name}] Attempt {retries + 1} failed: {e}")
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    
        # Exceeded retries
        duration_ms = (time.time() - start_time) * 1000.0
        err_msg = f"Failed to execute tool {self.name} after {self.max_retries + 1} attempts. Last error: {last_err}"
        
        event = ToolExecutionEvent(
            tool_name=self.name,
            arguments=arguments,
            status="error",
            duration_ms=duration_ms,
            retry_count=retries,
            error_message=err_msg
        )
        await record_tool_event(event)
        
        return ToolResult(
            status="error",
            content=None,
            error_message=err_msg,
            execution_time_ms=duration_ms,
            retry_count=retries
        )


class GitLabMCPTool(BaseMCPTool):
    """Wrapper for GitLab MCP tools with dynamic session support."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        # Don't set a static session_getter - we'll override get_session
        super().__init__(
            name=name,
            description=description,
            schema=schema,
            session_name="gitlab",
            session_getter=lambda: mcp_service.gitlab_session  # Fallback to global session
        )

    async def get_session(self, context: Optional[AgentContext] = None) -> Optional[Any]:
        """
        Get GitLab session for the current user from context.
        Falls back to global session for system operations.
        """
        # If context has user info, try to get their specific session
        if context and context.user and context.user.user_id:
            user_id = context.user.user_id
            project_id = context.repository.id if context.repository else None

            print(f"[INFO] GitLabMCPTool: Getting session for user {user_id}, project {project_id}")

            try:
                session = await mcp_service.get_gitlab_session_for_user(user_id, project_id)
                if session:
                    return session
                print(f"[WARN] GitLabMCPTool: Failed to get session for user {user_id}, falling back to global")
            except Exception as e:
                print(f"[ERROR] GitLabMCPTool: Error getting session for user {user_id}: {e}")

        # Fallback to global session (for system operations or when context unavailable)
        return mcp_service.gitlab_session

    async def execute(self, arguments: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        """Execute with dynamic session retrieval."""
        try:
            self.validate(arguments)
        except Exception as ve:
            return ToolResult(
                status="error",
                content=None,
                error_message=f"Validation failed: {ve}",
                execution_time_ms=0.0,
                retry_count=0
            )

        # Get session dynamically based on context
        session = await self.get_session(context)
        if not session:
            err_msg = f"Active session for {self.session_name} is not initialized/available"
            return ToolResult(
                status="error",
                content=None,
                error_message=err_msg,
                execution_time_ms=0.0,
                retry_count=0
            )

        start_time = time.time()
        retries = 0
        backoff = 1.0
        last_err = None

        while retries <= self.max_retries:
            try:
                print(f"[INFO] [MCPToolWrapper:{self.name}] Invoking... (Attempt {retries + 1}/{self.max_retries + 1})")

                # Subprocess call wrapping with timeout
                result = await asyncio.wait_for(
                    session.call_tool(name=self.name, arguments=arguments),
                    timeout=self.timeout
                )

                duration_ms = (time.time() - start_time) * 1000.0

                # Normalize output
                normalized_content = ""
                if hasattr(result, "content") and result.content:
                    normalized_content = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
                else:
                    normalized_content = str(result)

                try:
                    import json
                    normalized_content = json.loads(normalized_content)
                except:
                    pass

                # Record event using observability
                event = ToolExecutionEvent(
                    tool_name=self.name,
                    arguments=arguments,
                    status="success",
                    duration_ms=duration_ms,
                    retry_count=retries
                )
                await record_tool_event(event)

                return ToolResult(
                    status="success",
                    content=normalized_content,
                    execution_time_ms=duration_ms,
                    retry_count=retries
                )

            except Exception as e:
                last_err = e
                print(f"[WARN] [MCPToolWrapper:{self.name}] Attempt {retries + 1} failed: {e}")
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0

        # Exceeded retries
        duration_ms = (time.time() - start_time) * 1000.0
        err_msg = f"Failed to execute tool {self.name} after {self.max_retries + 1} attempts. Last error: {last_err}"

        event = ToolExecutionEvent(
            tool_name=self.name,
            arguments=arguments,
            status="error",
            duration_ms=duration_ms,
            retry_count=retries,
            error_message=err_msg
        )
        await record_tool_event(event)

        return ToolResult(
            status="error",
            content=None,
            error_message=err_msg,
            execution_time_ms=duration_ms,
            retry_count=retries
        )


class MongoMCPTool(BaseMCPTool):
    """Wrapper for MongoDB MCP tools."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        super().__init__(
            name=name,
            description=description,
            schema=schema,
            session_name="mongodb",
            session_getter=lambda: mcp_service.mongo_session
        )


class DynatraceMCPTool(BaseMCPTool):
    """Wrapper for Dynatrace MCP tools."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        super().__init__(
            name=name,
            description=description,
            schema=schema,
            session_name="dynatrace",
            session_getter=lambda: mcp_service.dynatrace_session
        )


class GitNexusMCPTool(BaseMCPTool):
    """Wrapper for GitNexus MCP tools."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        super().__init__(
            name=name,
            description=description,
            schema=schema,
            session_name="gitnexus",
            session_getter=lambda: mcp_service.nexus_session
        )


class SentryMCPTool(BaseMCPTool):
    """Wrapper for Sentry MCP tools."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        super().__init__(
            name=name,
            description=description,
            schema=schema,
            session_name="sentry",
            session_getter=lambda: mcp_service.sentry_session
        )
