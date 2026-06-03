from typing import Any, Dict
from agents.planner import StepSchema

class ReflectionLayer:
    """
    Evaluates execution results for quality standards and signals adjustments if needed.
    """
    
    async def evaluate_step_result(self, step: StepSchema, result: Any) -> bool:
        """
        Evaluate if a step's output is valid. Returns True if acceptable,
        or raises ValueError/RuntimeError if it fails reflection checks.
        """
        # 1. Check if tool returned a status dict indicating failure
        if isinstance(result, dict):
            if result.get("status") in ["failed", "error"]:
                raise RuntimeError(
                    f"Reflection check failed on step '{step.step_id}': Tool returned failure status. "
                    f"Message: {result.get('message', 'No detail message provided.')}"
                )
                
        # 2. Check if git/nexus exit code is non-zero
        if isinstance(result, dict) and "returncode" in result:
            code = result["returncode"]
            if code != 0:
                raise RuntimeError(
                    f"Reflection check failed on step '{step.step_id}': Command exited with code {code}. "
                    f"Stderr: {result.get('stderr', '')}"
                )
                
        # 3. Handle schema check alerts or critical warnings
        if step.tool_name == "run_schema_inspection" and isinstance(result, dict):
            if result.get("drift_detected") and result.get("risk_level") == "HIGH":
                print(f"[WARN] [Reflection] High risk schema drift detected in step '{step.step_id}'!")
                
        return True
