import json
from typing import Dict, Any, List, Optional
from google.genai import types
from agents.context import AgentContext
from agents.registry import ToolRegistry
from agents.base_tool import BaseTool, ToolResult


def convert_json_schema_to_gemini(schema: Dict[str, Any]) -> types.Schema:
    """Recursively converts standard JSON Schema to Gemini types.Schema."""
    prop_type = str(schema.get("type", "string")).upper()
    description = schema.get("description")
    enum = schema.get("enum")
    
    # Map types
    type_map = {
        "STRING": types.Type.STRING,
        "NUMBER": types.Type.NUMBER,
        "INTEGER": types.Type.INTEGER,
        "BOOLEAN": types.Type.BOOLEAN,
        "OBJECT": types.Type.OBJECT,
        "ARRAY": types.Type.ARRAY
    }
    gemini_type = type_map.get(prop_type, types.Type.STRING)
    
    properties = {}
    if prop_type == "OBJECT" and "properties" in schema:
        for k, v in schema["properties"].items():
            if k == "repo":  # Skip repo parameter from client parameters
                continue
            properties[k] = convert_json_schema_to_gemini(v)
            
    items = None
    if prop_type == "ARRAY" and "items" in schema:
        items = convert_json_schema_to_gemini(schema["items"])
        
    required = schema.get("required")
    if required:
        required = [r for r in required if r != "repo"]
        
    return types.Schema(
        type=gemini_type,
        description=description,
        enum=enum,
        properties=properties or None,
        required=required or None,
        items=items
    )


class GeminiToolAdapter:
    """
    Converts and routes ToolRegistry tools to Gemini SDK Function Calling format,
    while enforcing execution limits, loop prevention, and user permission checks.
    """
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        # Tracks task_id -> list of executed tool names
        self._invocation_history: Dict[str, List[str]] = {}
        self.chaining_limit = 15

    def _is_mutate_action(self, tool_name: str) -> bool:
        """Determines if a tool performs modifying/mutating actions."""
        mutate_keywords = {"create", "update", "delete", "post", "write", "apply", "hotfix", "push", "patch"}
        name_lower = tool_name.lower()
        if any(keyword in name_lower for keyword in mutate_keywords):
            return True
        return False

    def get_gemini_tools(self) -> List[types.Tool]:
        """
        Translates all registered Tools in ToolRegistry to Gemini SDK types.Tool objects.
        """
        function_declarations = []
        for tool in self.registry.list_tools():
            schema = tool.get_schema()
            properties = schema.get("parameters", {}).get("properties", {})
            required = schema.get("parameters", {}).get("required", [])
            
            # Map parameters
            param_properties = {}
            for prop_name, prop_def in properties.items():
                if prop_name == "repo":
                    continue
                param_properties[prop_name] = convert_json_schema_to_gemini(prop_def)
                
            parameters = types.Schema(
                type=types.Type.OBJECT,
                properties=param_properties,
                required=[r for r in required if r != "repo"] or None
            )
            
            decl = types.FunctionDeclaration(
                name=tool.get_name(),
                description=tool.get_description(),
                parameters=parameters
            )
            function_declarations.append(decl)
            
        return [types.Tool(function_declarations=function_declarations)]

    async def execute_tool_with_guardrails(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """
        Validates permission states, invocation limits, and loops before executing tool.
        """
        task_id = context.task_id
        
        # 1. Chaining / Loop Guardrail
        if task_id not in self._invocation_history:
            self._invocation_history[task_id] = []
            
        history = self._invocation_history[task_id]
        if len(history) >= self.chaining_limit:
            err_msg = f"Security Violation: Chaining limit of {self.chaining_limit} tool calls reached for task {task_id}."
            print(f"[ERROR] [GeminiToolAdapter] {err_msg}")
            return ToolResult(
                status="error",
                content=None,
                error_message=err_msg,
                execution_time_ms=0.0,
                retry_count=0
            )

        # 2. Permission Guardrail
        if self._is_mutate_action(name):
            user_perms = context.user.permissions
            # Check if user has write/admin rights
            if not any(p in user_perms for p in ["write", "admin"]):
                err_msg = f"Security Violation: User {context.user.user_id} does not have required permissions ('write' or 'admin') to execute mutating tool '{name}'."
                print(f"[ERROR] [GeminiToolAdapter] {err_msg}")
                return ToolResult(
                    status="error",
                    content=None,
                    error_message=err_msg,
                    execution_time_ms=0.0,
                    retry_count=0
                )

        # 3. Recursive Call Guardrail
        args_str = json.dumps(arguments).lower()
        if "execute_tool" in args_str or "call_tool" in args_str:
            err_msg = f"Security Violation: Recursive tool call injection pattern detected in arguments."
            print(f"[ERROR] [GeminiToolAdapter] {err_msg}")
            return ToolResult(
                status="error",
                content=None,
                error_message=err_msg,
                execution_time_ms=0.0,
                retry_count=0
            )

        # 4. Check for Consecutive Duplicate Loops
        if len(history) >= 3 and all(h == name for h in history[-3:]):
            err_msg = f"Security Violation: Consecutive duplicate tool calls loop detected for tool '{name}'."
            print(f"[ERROR] [GeminiToolAdapter] {err_msg}")
            return ToolResult(
                status="error",
                content=None,
                error_message=err_msg,
                execution_time_ms=0.0,
                retry_count=0
            )

        # Record tool invocation in tracking history
        history.append(name)
        
        # 5. Execute
        try:
            tool = self.registry.get_tool(name)
            result = await tool.execute(arguments, context)
            return result
        except Exception as e:
            return ToolResult(
                status="error",
                content=None,
                error_message=str(e),
                execution_time_ms=0.0,
                retry_count=0
            )
