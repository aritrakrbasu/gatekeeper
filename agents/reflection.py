from typing import TYPE_CHECKING, Any, Optional

from agents.planner import StepSchema
from peil.models.enums import CaptureEventType

if TYPE_CHECKING:
    from agents.aril_bridge import ArilSession


class ReflectionLayer:
    """
    Evaluates execution results for quality standards and signals adjustments if needed.
    """

    async def evaluate_step_result(
        self,
        step: StepSchema,
        result: Any,
        aril: Optional["ArilSession"] = None,
    ) -> bool:
        """
        Evaluate if a step's output is valid. Returns True if acceptable,
        or raises ValueError/RuntimeError if it fails reflection checks.
        """
        passed = True
        reason: Optional[str] = None
        warning: Optional[str] = None

        try:
            if isinstance(result, dict):
                if result.get("status") in ["failed", "error"]:
                    passed = False
                    reason = (
                        f"Tool returned failure status. "
                        f"Message: {result.get('message', 'No detail message provided.')}"
                    )
                    raise RuntimeError(
                        f"Reflection check failed on step '{step.step_id}': {reason}"
                    )

            if isinstance(result, dict) and "returncode" in result:
                code = result["returncode"]
                if code != 0:
                    passed = False
                    reason = f"Command exited with code {code}. Stderr: {result.get('stderr', '')}"
                    raise RuntimeError(
                        f"Reflection check failed on step '{step.step_id}': {reason}"
                    )

            if step.tool_name == "run_schema_inspection" and isinstance(result, dict):
                if result.get("drift_detected") and result.get("risk_level") == "HIGH":
                    warning = "High risk schema drift detected"
                    print(f"[WARN] [Reflection] High risk schema drift detected in step '{step.step_id}'!")

            return True
        except Exception as exc:
            passed = False
            reason = reason or str(exc)
            raise
        finally:
            if aril is not None:
                try:
                    aril.emit(
                        CaptureEventType.REFLECTION_EVALUATED,
                        {
                            "step_id": step.step_id,
                            "passed": passed,
                            "reason": reason,
                            "warning": warning,
                        },
                    )
                except Exception as emit_exc:
                    print(f"[WARN] [Reflection] ARIL emit failed: {emit_exc}")
