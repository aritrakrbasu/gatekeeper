import uuid
from typing import Dict, Any, Optional
from opentelemetry import trace, context
from opentelemetry.baggage import set_baggage
from opentelemetry.context import Context
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

    # Get tracer for creating manual span
    tracer = trace.get_tracer(__name__)

    # Use OpenTelemetry baggage to propagate attributes to all child spans
    project_id = str(payload.get("project", {}).get("id", "unknown"))
    user_id = str(payload.get("user", {}).get("id", "unknown"))

    otel_ctx = Context()
    if user_id:
        otel_ctx = set_baggage("user.id", str(user_id), context=otel_ctx)
    if mr_iid:
        otel_ctx = set_baggage("mr.id", str(mr_iid), context=otel_ctx)
    if project_id:
        otel_ctx = set_baggage("repository.id", str(project_id), context=otel_ctx)
    otel_ctx = set_baggage("operation.type", "mr_review", context=otel_ctx)

    token = context.attach(otel_ctx)
    try:
        with tracer.start_as_current_span("mr_review_workflow") as parent_span:
            # Also set directly on span for visibility
            if user_id:
                parent_span.set_attribute("user.id", str(user_id))
            if mr_iid:
                parent_span.set_attribute("mr.id", str(mr_iid))
            if project_id:
                parent_span.set_attribute("repository.id", str(project_id))
            parent_span.set_attribute("operation.type", "mr_review")

            print(f"[INFO] MR review workflow span created with attributes: user_id={user_id}, mr_id={mr_iid}, repository_id={project_id}")

            # 1. Aggregates information from services & create snapshot context
            builder = ContextBuilder()
            agent_context = await builder.build_context(task_id, objective, payload)

            # 2. Build Tool Registry
            registry = await build_default_registry()

            # 3. Instantiate and run WorkflowEngine
            engine = WorkflowEngine(registry)
            result = await engine.run_task(agent_context)

    finally:
        context.detach(token)

    return result


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

    # Get tracer for creating manual span
    tracer = trace.get_tracer(__name__)

    # Use OpenTelemetry baggage to propagate attributes to all child spans
    otel_ctx = Context()
    if problem_id:
        otel_ctx = set_baggage("dynatrace.problem_id", str(problem_id), context=otel_ctx)
    otel_ctx = set_baggage("operation.type", "incident_workflow", context=otel_ctx)

    token = context.attach(otel_ctx)
    try:
        with tracer.start_as_current_span("incident_workflow") as parent_span:
            # Also set directly on span for visibility
            if problem_id:
                parent_span.set_attribute("dynatrace.problem_id", str(problem_id))
            parent_span.set_attribute("operation.type", "incident_workflow")

            print(f"[INFO] Incident workflow span created with attributes: problem_id={problem_id}")

            # 1. Aggregates incident & project context
            builder = ContextBuilder()
            agent_context = await builder.build_context(task_id, objective, payload)

            # 2. Build Tool Registry
            registry = await build_default_registry()

            # 3. Run task on engine
            engine = WorkflowEngine(registry)
            result = await engine.run_task(agent_context)

    finally:
        context.detach(token)

    return result


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

    # Get tracer for creating manual span
    tracer = trace.get_tracer(__name__)

    # Use OpenTelemetry baggage to propagate attributes to all child spans
    otel_ctx = Context()
    if problem_id:
        otel_ctx = set_baggage("dynatrace.problem_id", str(problem_id), context=otel_ctx)
    otel_ctx = set_baggage("operation.type", "auto_remediation", context=otel_ctx)

    token = context.attach(otel_ctx)
    try:
        with tracer.start_as_current_span("auto_remediation_workflow") as parent_span:
            # Also set directly on span for visibility
            if problem_id:
                parent_span.set_attribute("dynatrace.problem_id", str(problem_id))
            parent_span.set_attribute("operation.type", "auto_remediation")

            print(f"[INFO] Auto remediation workflow span created with attributes: problem_id={problem_id}")

            # 1. Aggregates context
            builder = ContextBuilder()
            agent_context = await builder.build_context(task_id, objective, payload)

            # 2. Build Tool Registry
            registry = await build_default_registry()

            # 3. Run task on engine
            engine = WorkflowEngine(registry)
            result = await engine.run_task(agent_context)

    finally:
        context.detach(token)

    return result


def _is_breaking_bug(payload: Dict[str, Any]) -> bool:
    """Detect if Sentry issue is a breaking bug (production + error/fatal)."""
    environment = str(payload.get("environment", "")).lower()
    level = str(payload.get("level", "")).lower()
    return environment == "production" and level in ["error", "fatal"]


async def run_sentry_bug_workflow(payload: Dict[str, Any], user_id: Optional[str] = None, username: Optional[str] = None, target_project_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sentry Bug Workflow:
    Breaking Bug Detection -> Context Build -> Sentry MCP -> GitLab REST API -> Gemini Analysis -> Draft MR Creation

    Note: This workflow uses direct GitLab REST API calls (via local tools) instead of GitLab MCP.

    Args:
        payload: Sentry webhook payload (nested structure)
        user_id: Optional user ID for GitLab operations (defaults to sentry-operator)
        username: Optional username for GitLab operations
        target_project_id: Optional GitLab project ID (defaults to value from payload or '82576405')
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Normalize payload (handle nested Sentry webhook structure)
        from agents.context import normalize_sentry_payload
        normalized = normalize_sentry_payload(payload)

        # 1. Check if breaking bug
        if not _is_breaking_bug(normalized):
            return {
                "status": "ignored",
                "reason": "Not a breaking bug (only production error/fatal issues are processed)",
                "environment": normalized.get("environment"),
                "level": normalized.get("level")
            }

        issue_id = normalized.get("issue_id", "unknown")
        logger.info(f"Processing Sentry issue {issue_id}")

        # Get tracer for creating manual span
        tracer = trace.get_tracer(__name__)

        # Use OpenTelemetry baggage to propagate attributes to all child spans
        # Baggage is specifically designed for cross-boundary context propagation
        otel_ctx = Context()
        if user_id:
            otel_ctx = set_baggage("user.id", str(user_id), context=otel_ctx)
        if issue_id:
            otel_ctx = set_baggage("sentry.issue_id", str(issue_id), context=otel_ctx)
        if target_project_id:
            otel_ctx = set_baggage("repository.id", str(target_project_id), context=otel_ctx)
        otel_ctx = set_baggage("operation.type", "sentry_bug_workflow", context=otel_ctx)

        # Create a manual span with the baggage context
        token = context.attach(otel_ctx)
        try:
            with tracer.start_as_current_span("sentry_bug_workflow") as parent_span:
                # Also set directly on span for visibility
                if user_id:
                    parent_span.set_attribute("user.id", str(user_id))
                if issue_id:
                    parent_span.set_attribute("sentry.issue_id", str(issue_id))
                if target_project_id:
                    parent_span.set_attribute("repository.id", str(target_project_id))
                parent_span.set_attribute("operation.type", "sentry_bug_workflow")

                print(f"[INFO] Sentry workflow span created with attributes: user_id={user_id}, issue_id={issue_id}, repository_id={target_project_id}")

                # 2. Build context using normalized payload and user credentials
                agent_context = await ContextBuilder.build_from_sentry_issue(normalized, user_id=user_id, username=username, target_project_id=target_project_id)

                # 3. Build Tool Registry for Sentry workflow (uses local GitLab API tools, not GitLab MCP)
                registry = await build_sentry_registry()

                # 4. Execute workflow with Gemini AI (this will now inherit the baggage context)
                engine = WorkflowEngine(registry)
                result = await engine.run_task(agent_context)

        finally:
            context.detach(token)

        return {
            "status": "completed",
            "issue_id": issue_id,
            "result": result
        }

    except Exception as e:
        logger.error(f"Failed to process Sentry webhook: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


async def build_sentry_registry():
    """
    Build a tool registry specifically for Sentry workflows.

    This registry includes:
    - All local Python tools (including new GitLab REST API tools)
    - Sentry MCP (for fetching issue details)
    - MongoDB, Dynatrace, GitNexus MCP sessions

    Notably EXCLUDES GitLab MCP, as we use direct GitLab REST API calls instead.
    """
    from services import mcp_service
    from agents import tools
    from agents.registry import ToolRegistry

    registry = ToolRegistry()

    # 1. Register all local Python tools (including GitLab REST API tools)
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

    # 2. Register active MCP sessions (EXCLUDING GitLab MCP)
    # MongoDB
    if mcp_service.mongo_session:
        await registry.register_mcp_session("mongodb", mcp_service.mongo_session)
    # GitNexus
    if mcp_service.nexus_session:
        await registry.register_mcp_session("gitnexus", mcp_service.nexus_session)
    # Dynatrace
    if mcp_service.dynatrace_session:
        await registry.register_mcp_session("dynatrace", mcp_service.dynatrace_session)
    # Sentry (for fetching issue details)
    if mcp_service.sentry_session:
        await registry.register_mcp_session("sentry", mcp_service.sentry_session)

    # Note: GitLab MCP is intentionally NOT registered here
    # We use local GitLab REST API tools instead

    return registry
