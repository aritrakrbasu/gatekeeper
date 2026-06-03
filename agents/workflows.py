import uuid
from typing import Dict, Any
from agents.context import ContextBuilder
from agents.registry import build_default_registry
from agents.engine import WorkflowEngine

async def run_mr_review_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    MR Review Workflow: 
    Diff -> Context Build -> Impact Analysis -> Memory Retrieval -> Agent Review -> Findings
    """
    mr_iid = payload.get("object_attributes", {}).get("iid", "unknown")
    task_id = f"mr-review-{uuid.uuid4().hex[:8]}"
    objective = (
        f"Perform a comprehensive review on GitLab MR #{mr_iid}. "
        "The review must clone the repository, run GitNexus call-graph analysis, fetch the MR diff, "
        "run static impact analysis, perform schema drift inspection, summarize all findings, "
        "and post a detailed markdown comment on the MR."
    )
    
    # 1. Aggregates information from services & create snapshot context
    builder = ContextBuilder()
    context = await builder.build_context(task_id, objective, payload)
    
    # 2. Build Tool Registry
    registry = await build_default_registry()
    
    # 3. Instantiate and run WorkflowEngine
    engine = WorkflowEngine(registry)
    return await engine.run_task(context)


async def run_incident_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Incident Workflow: 
    Alert -> Dynatrace Analysis -> Impact Analysis -> Root Cause Detection -> Fix Proposal
    """
    problem_id = payload.get("problem_id", "unknown")
    task_id = f"incident-{problem_id}-{uuid.uuid4().hex[:8]}"
    objective = (
        f"Investigate Dynatrace alert incident problem_id {problem_id}. "
        "You must fetch the Dynatrace Grails logs, identify the traceback/exception root cause, "
        "compile a detailed diagnosis, and propose a hotfix diff code snippet."
    )
    
    # 1. Aggregates incident & project context
    builder = ContextBuilder()
    context = await builder.build_context(task_id, objective, payload)
    
    # 2. Build Tool Registry
    registry = await build_default_registry()
    
    # 3. Run task on engine
    engine = WorkflowEngine(registry)
    return await engine.run_task(context)


async def run_auto_remediation_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto Remediation Workflow: 
    Issue/Alert -> Plan -> Generate Patch -> Validate -> Approval -> Merge Request
    """
    problem_id = payload.get("problem_id", "unknown")
    task_id = f"remediation-{problem_id}-{uuid.uuid4().hex[:8]}"
    objective = (
        f"Diagnose and automatically self-heal Dynatrace incident {problem_id}. "
        "You must fetch Dynatrace logs, clone the repository, write a surgical patch file, "
        "apply the hotfix patch locally, validate it, request human approval, and open a GitLab Merge Request."
    )
    
    # 1. Aggregates context
    builder = ContextBuilder()
    context = await builder.build_context(task_id, objective, payload)
    
    # 2. Build Tool Registry
    registry = await build_default_registry()
    
    # 3. Run task on engine
    engine = WorkflowEngine(registry)
    return await engine.run_task(context)
