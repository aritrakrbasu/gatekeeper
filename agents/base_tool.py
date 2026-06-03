import time
import inspect
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from pydantic import BaseModel, Field
from agents.context import AgentContext
from agents.observability import ToolExecutionEvent, record_tool_event


class ToolResult(BaseModel):
    """Normalized output representation of any tool execution."""
    status: str = Field(description="Execution outcome: 'success' or 'error'")
    content: Any = Field(description="The normalized payload output from the tool execution")
    error_message: Optional[str] = Field(default=None, description="Detailed error description if execution failed")
    execution_time_ms: float = Field(default=0.0, description="Duration of tool execution in milliseconds")
    retry_count: int = Field(default=0, description="Number of retries attempted during execution")


class BaseTool(ABC):
    """
    Formal interface for all local and MCP-bridged agent tools.
    Enforces validation, execution wrappers, timeouts, and retries.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Returns the unique identifier name of the tool."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Returns a clear explanation of what the tool accomplishes."""
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Returns the JSON Schema of the parameters expected by this tool."""
        pass

    @abstractmethod
    def validate(self, arguments: Dict[str, Any]) -> None:
        """
        Validates the provided arguments against the tool's JSON schema.
        Raises ValueError if validation fails.
        """
        pass

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: AgentContext) -> ToolResult:
        """
        Executes the tool's core logic with the resolved arguments and AgentContext.
        Returns a normalized ToolResult.
        """
        pass


class LocalTool(BaseTool):
    """
    Wrapper bridging direct Python function callbacks to the BaseTool interface.
    """
    def __init__(self, name: str, description: str, schema: Dict[str, Any], callback: Callable):
        self.name = name
        self.description = description
        self.schema = schema
        self.callback = callback

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

        start_time = time.time()
        try:
            if inspect.iscoroutinefunction(self.callback):
                res = await self.callback(**arguments)
            else:
                res = self.callback(**arguments)
            
            duration_ms = (time.time() - start_time) * 1000.0
            
            event = ToolExecutionEvent(
                tool_name=self.name,
                arguments=arguments,
                status="success",
                duration_ms=duration_ms,
                retry_count=0
            )
            await record_tool_event(event)

            return ToolResult(
                status="success",
                content=res,
                execution_time_ms=duration_ms,
                retry_count=0
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000.0
            err_msg = f"Failed to execute local tool {self.name}: {e}"
            
            event = ToolExecutionEvent(
                tool_name=self.name,
                arguments=arguments,
                status="error",
                duration_ms=duration_ms,
                retry_count=0,
                error_message=err_msg
            )
            await record_tool_event(event)
            
            return ToolResult(
                status="error",
                content=None,
                error_message=err_msg,
                execution_time_ms=duration_ms,
                retry_count=0
            )
