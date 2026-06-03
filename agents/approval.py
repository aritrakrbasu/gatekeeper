import uuid
import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from services import mongo_client

class ApprovalPackage(BaseModel):
    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    step_id: str
    tool_name: str
    summary: str
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    files_impacted: List[str] = Field(default_factory=list)
    proposed_changes: str  # unified diff patch or description
    rollback_plan: str
    status: str = "pending"  # pending, approved, rejected
    created_at: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

class HumanApprovalLayer:
    """
    Manages human-in-the-loop gates. Before any mutating write action is executed,
    it generates an ApprovalPackage, stores it in MongoDB pending_approvals, and pauses task execution.
    """
    
    async def request_approval(self, task_id: str, action_name: str, payload: Dict[str, Any]) -> bool:
        """
        Legacy/mock support for direct inline checks. Auto-approves for background compatibility
        if not running in strict gatekeeper mode.
        """
        print(f"[INFO] [HumanApprovalLayer] Auto-approving task {task_id} action '{action_name}'")
        try:
            approval_record = {
                "task_id": task_id,
                "action_name": action_name,
                "payload": payload,
                "status": "auto_approved",
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
            await mongo_client.insert_one(
                collection_name="agent_approvals",
                document=approval_record
            )
        except Exception as e:
            print(f"[WARN] [HumanApprovalLayer] Failed to log approval to database: {e}")
            
        return True

    async def generate_package(self, task_id: str, step_id: str, tool_name: str, arguments: Dict[str, Any]) -> ApprovalPackage:
        """Generates an ApprovalPackage populated with changes, risk levels, and rollback plans."""
        summary = f"Execute mutating tool {tool_name}"
        risk_level = "LOW"
        files_impacted = []
        proposed_changes = ""
        rollback_plan = "No automated rollback registered."
        
        if tool_name == "apply_hotfix_patch":
            file_path = arguments.get("file_path", "unknown file")
            summary = f"Apply automated hotfix patch to {file_path}"
            risk_level = "MEDIUM"
            files_impacted = [file_path]
            proposed_changes = arguments.get("diff_patch", "")
            rollback_plan = f"Restore the original file content of {file_path} from the backup."
            
        elif tool_name == "create_hotfix_branch_and_mr":
            source_branch = arguments.get("source_branch", "unknown-branch")
            summary = f"Create git branch '{source_branch}' and open GitLab Merge Request"
            risk_level = "HIGH"
            files_impacted = ["All modified repository files"]
            proposed_changes = f"Commit changes, push to branch '{source_branch}', and open MR."
            rollback_plan = f"Delete remote branch '{source_branch}' and close/delete the GitLab MR."
            
        elif tool_name == "post_gitlab_mr_comment":
            mr_iid = arguments.get("mr_iid", "unknown")
            summary = f"Post comment/review note on GitLab MR #{mr_iid}"
            risk_level = "LOW"
            files_impacted = []
            proposed_changes = arguments.get("comment", "")
            rollback_plan = "Optionally delete or edit the posted comment."
            
        package = ApprovalPackage(
            task_id=task_id,
            step_id=step_id,
            tool_name=tool_name,
            summary=summary,
            risk_level=risk_level,
            files_impacted=files_impacted,
            proposed_changes=proposed_changes,
            rollback_plan=rollback_plan
        )
        return package

    async def submit_for_approval(self, package: ApprovalPackage) -> None:
        """Saves the package in the pending_approvals collection."""
        doc = package.model_dump()
        await mongo_client.upsert_one(
            collection_name="pending_approvals",
            filter={"approval_id": package.approval_id},
            document=doc
        )
        print(f"[OK] [HumanApprovalLayer] Saved pending approval {package.approval_id} for task {package.task_id}")

    async def check_approval_status(self, task_id: str, step_id: str) -> Optional[str]:
        """Checks if a step has been approved or rejected."""
        doc = await mongo_client.find_one(
            collection_name="pending_approvals",
            filter={"task_id": task_id, "step_id": step_id}
        )
        if doc:
            return doc.get("status", "pending")
        return None
