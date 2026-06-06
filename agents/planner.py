import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from google.genai import types
from opentelemetry import trace
from services.gemini_service import ai_client
from agents.context import AgentContext
from agents.registry import ToolRegistry

class StepSchema(BaseModel):
    step_id: str = Field(description="Unique identifier for the step (e.g. clone_step, schema_step)")
    tool_name: str = Field(description="The exact name of the tool to execute")
    arguments_json: str = Field(description="JSON string representing the arguments key-value dictionary to pass to the tool. E.g. '{\"repo_path\": \"/tmp/repo\"}'. Can use '{{step_id.result}}' in values.")
    dependencies: List[str] = Field(default_factory=list, description="List of step_ids that must complete before this step is executed")
    action: str = Field(description="Human readable description of what action is taken in this step")
    reason: str = Field(description="Explicit reasoning and tool justification for running this step")

class PlanSchema(BaseModel):
    explanation: str = Field(description="Brief explanation of the plan strategy")
    steps: List[StepSchema] = Field(description="The steps of the DAG plan")

class PlannerAgent:
    """
    Constructs and refines step-by-step DAG execution plans using Gemini.
    Enforces maximum 10 steps and maximum 3 mutating (write) actions.
    """
    
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name

    def _is_mutate_action(self, tool_name: str) -> bool:
        """Determines if a tool performs modifying/mutating actions."""
        mutate_keywords = {"create", "update", "delete", "post", "write", "apply", "hotfix", "push", "patch"}
        name_lower = tool_name.lower()
        return any(keyword in name_lower for keyword in mutate_keywords)

    def _serialize_tools(self, registry: ToolRegistry) -> str:
        serialized = []
        for name, tool in registry._tools.items():
            schema = tool.get_schema()
            desc = tool.get_description() or schema.get("description", "No description available.")
            params = schema.get("parameters", {})
            serialized.append(
                f"Tool Name: {name}\n"
                f"Description: {desc}\n"
                f"Parameters: {json.dumps(params, indent=2)}\n"
                f"---"
            )
        return "\n".join(serialized)

    async def generate_plan(
        self,
        context: AgentContext,
        registry: ToolRegistry,
        history_steps: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None
    ) -> List[StepSchema]:
        """
        Queries Gemini to construct a dependency-based PlanStep DAG.
        Enforces strict limits of <= 10 steps and <= 3 write actions.
        """
        tools_description = self._serialize_tools(registry)
        
        system_instruction = (
            "You are the elite Gatekeeper AI Planner. Your job is to construct a DAG execution plan (list of steps with dependencies) to satisfy the given objective.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You MUST generate a maximum of 10 steps.\n"
            "2. You MUST have at most 3 write/mutating actions (e.g. committing, applying hotfixes, pushing MRs, writing comments).\n"
            "3. You must justify each step inside the 'reason' field and describe the action in the 'action' field.\n\n"
            "Rules for arguments:\n"
            "1. You must write arguments as a valid, escaped JSON string inside 'arguments_json'. E.g. '{\"repo_path\": \"/tmp/repo\"}'. Do not output structured dictionaries directly in arguments_json, only a flat JSON string.\n"
            "2. Inside the JSON string, you must use exact tool parameter names as defined.\n"
            "3. If a step depends on the output of a previous step, include that step's ID in 'dependencies' and use the template token '{{step_id.result}}' or a nested dictionary path like '{{step_id.result.markdown_report}}' inside the values of the JSON string.\n"
            "4. Be precise. Only generate plans using the registered tools below.\n"
            "5. For Merge Request reviews, the standard sequence is:\n"
            "   a. Clone the repository baseline (stay on target branch) via 'clone_repo'.\n"
            "   b. Run 'gitnexus_analyze' on the cloned repository path.\n"
            "   c. Get MR diffs using 'get_gitlab_mr_diffs'.\n"
            "   d. Run 'run_impact_analysis' on the repo path.\n"
            "   e. Run 'run_schema_inspection' on the diff text.\n"
            "   f. Use Gemini to summarize findings and post comments using 'post_gitlab_mr_comment'.\n"
            "6. For Dynatrace incident self-healing, the standard sequence is:\n"
            "   a. Fetch incident details from Dynatrace Grail via 'get_dynatrace_incident_details'.\n"
            "   b. Clone repository baseline via 'clone_repo'.\n"
            "   c. Use Gemini to diagnose and write a surgical diff patch code.\n"
            "   d. Apply diff patch to file using 'apply_hotfix_patch'.\n"
            "   e. Commit, push branch and open GitLab MR using 'create_hotfix_branch_and_mr'.\n"
        )
        
        prompt = (
            f"OBJECTIVE: {context.objective}\n"
            f"REPOSITORY ID: {context.repository.id}\n"
            f"REPOSITORY NAME: {context.repository.name}\n"
            f"GIT URL: {context.repository.git_url}\n"
            f"SOURCE BRANCH: {context.branch.source_branch}\n"
            f"TARGET BRANCH: {context.branch.target_branch}\n"
            f"USER ID: {context.user.user_id}\n\n"
            f"AVAILABLE TOOLS:\n{tools_description}\n\n"
        )
        
        if memories:
            prompt += (
                f"HISTORICAL SIMILAR MEMORIES RETRIEVED:\n"
                f"{json.dumps(memories, indent=2)}\n"
                f"Use this context to inform your plan strategy (e.g. reuse successful patch designs or root causes).\n\n"
            )

        if history_steps:
            prompt += (
                f"PREVIOUS EXECUTION STEPS HISTORY (some steps may have failed):\n"
                f"{json.dumps(history_steps, indent=2)}\n\n"
                f"Please adjust the plan to recover from any failures. If a recovery is not possible, design a step to report/post the failure comment and exit cleanly.\n\n"
            )
            
        print(f"[INFO] [Planner] Asking Gemini to build/adjust plan...")

        # Get current span to add context attributes for observability
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            # Log planning context for debugging
            print(f"[INFO] [Planner] Planning within span context: {current_span.name}")

        response = ai_client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=PlanSchema
            )
        )
        
        try:
            plan_data = PlanSchema.model_validate_json(response.text.strip())
            
            # Guardrail Validations
            steps = plan_data.steps
            if len(steps) > 10:
                raise ValueError(f"Plan validation failed: plan has {len(steps)} steps, which exceeds the max limit of 10.")
                
            write_count = sum(1 for s in steps if self._is_mutate_action(s.tool_name))
            if write_count > 3:
                raise ValueError(f"Plan validation failed: plan has {write_count} write/mutating actions, which exceeds the max limit of 3.")

            print(f"[OK] [Planner] Plan successfully generated. Explanation: '{plan_data.explanation}'")
            for i, step in enumerate(plan_data.steps):
                print(f"     Step {i+1}: {step.step_id} -> {step.tool_name} (depends on: {step.dependencies})")
            return plan_data.steps
        except Exception as e:
            print(f"[ERROR] [Planner] Failed to parse planning output: {e}\nResponse text:\n{response.text}")
            raise

# Export alias to avoid breaking imports in other modules
Planner = PlannerAgent
