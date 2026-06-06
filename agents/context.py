import uuid
import datetime
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from services import repository_service, user_service, mongo_client


def normalize_sentry_payload(payload: dict) -> dict:
    """
    Normalize Sentry webhook payload to a flat structure.

    Sentry webhooks have nested structure (data.error) with tags as arrays.
    This converts to the flat structure expected by ContextBuilder.
    """
    # If already normalized (has issue_id at root), return as-is
    if "issue_id" in payload and isinstance(payload.get("tags"), dict):
        return payload

    # Extract the error event from nested structure
    error_event = payload.get("data", {}).get("error", {})
    if not error_event:
        return payload

    # Convert tags from array of [key, value] to dict
    tags_array = error_event.get("tags", [])
    tags_dict = {}
    for tag_pair in tags_array:
        if isinstance(tag_pair, (list, tuple)) and len(tag_pair) >= 2:
            tags_dict[tag_pair[0]] = tag_pair[1]

    # Build exception message from stacktrace
    exception_values = error_event.get("exception", {}).get("values", [])
    stack_trace = ""
    if exception_values:
        exc_value = exception_values[0]
        stack_trace = exc_value.get("value", "")
        if not stack_trace:
            # Try to build from stacktrace frames
            frames = exc_value.get("stacktrace", {}).get("frames", [])
            if frames:
                for frame in frames:
                    func = frame.get("function", "?")
                    filename = frame.get("filename", "?")
                    lineno = frame.get("lineno", "?")
                    stack_trace += f"  at {func} ({filename}:{lineno})\n"

    # Get project ID (may be a number in webhooks)
    project_id = error_event.get("project", "")
    if isinstance(project_id, (int, float)):
        project_id = str(project_id)

    # Build normalized payload
    normalized = {
        "issue_id": error_event.get("issue_id", ""),
        "title": error_event.get("title", ""),
        "level": error_event.get("level", ""),
        "environment": error_event.get("environment", ""),
        "culprit": error_event.get("culprit", ""),
        "message": stack_trace or error_event.get("message", ""),
        "project": project_id,
        "release": error_event.get("release", ""),
        "platform": error_event.get("platform", ""),
        "transaction": error_event.get("transaction", ""),
        "event_id": error_event.get("event_id", ""),
        "url": error_event.get("request", {}).get("url", ""),
        "tags": tags_dict,
        "stacktrace": exception_values[0].get("stacktrace", {}).get("frames", []) if exception_values else []
    }

    return normalized


class RepositoryContext(BaseModel):
    id: str
    name: str
    git_url: Optional[str] = None
    visibility: Optional[str] = "private"
    owner: Optional[str] = None
    repo_path: Optional[str] = None


class BranchContext(BaseModel):
    source_branch: str
    target_branch: str
    base_commit_sha: Optional[str] = None
    head_commit_sha: Optional[str] = None


class UserContext(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    permissions: List[str] = Field(default_factory=lambda: ["read"])


class SchemaContext(BaseModel):
    db_name: Optional[str] = None
    collections: List[str] = Field(default_factory=list)
    last_schema_scan: Optional[str] = None


class IncidentContext(BaseModel):
    problem_id: Optional[str] = None
    title: Optional[str] = None
    severity: Optional[str] = "MEDIUM"
    impacted_entity: Optional[str] = None
    stack_trace: Optional[str] = None


class SentryIssueContext(BaseModel):
    """Context for Sentry issue events."""
    issue_id: str
    title: str
    level: str
    environment: str
    culprit: Optional[str] = None
    stack_trace: Optional[str] = None
    affected_files: List[str] = Field(default_factory=list)
    git_commit_sha: Optional[str] = None


class DeploymentContext(BaseModel):
    environment: str = "production"
    cluster_name: Optional[str] = None
    active_version: Optional[str] = None


class HistoricalMemoryContext(BaseModel):
    recent_tasks: List[str] = Field(default_factory=list)
    execution_traces_count: int = 0


class AgentContext(BaseModel):
    version: int = 1
    task_id: str
    objective: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    repository: RepositoryContext
    branch: BranchContext
    user: UserContext
    schema_ctx: SchemaContext
    incident: Optional[IncidentContext] = None
    sentry_issue: Optional[SentryIssueContext] = None
    deployment: Optional[DeploymentContext] = None
    history: HistoricalMemoryContext = Field(default_factory=HistoricalMemoryContext)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def repository_id(self) -> str:
        return self.repository.id

    @property
    def repository_path(self) -> str:
        if self.repository.repo_path:
            return self.repository.repo_path
        return f"workspace/{self.repository.name}"

    @property
    def source_branch(self) -> str:
        return self.branch.source_branch

    @property
    def target_branch(self) -> str:
        return self.branch.target_branch

    @property
    def user_id(self) -> str:
        return self.user.user_id

    def serialize(self) -> Dict[str, Any]:
        return self.model_dump()

    def update(self, **kwargs) -> "AgentContext":
        """Returns a copy of the context with updated fields and incremented version."""
        data = self.model_dump()
        for key, value in kwargs.items():
            if key in data:
                if isinstance(data[key], dict) and isinstance(value, dict):
                    data[key].update(value)
                else:
                    data[key] = value
            else:
                data[key] = value
        data["version"] = self.version + 1
        return AgentContext(**data)


class ContextBuilder:
    """
    Asynchronously aggregates information from services, normalizes it,
    and returns a snapshot version of AgentContext with TTL caching.
    """
    def __init__(self, cache_ttl_seconds: int = 300):
        self.ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[datetime.datetime, AgentContext]] = {}

    def _get_cache_key(self, task_id: str, payload: dict) -> str:
        """Constructs a cache key based on project id and branch/problem info."""
        project_id = str(payload.get("project", {}).get("id") or payload.get("project_id", ""))
        mr_iid = str(payload.get("object_attributes", {}).get("iid") or "")
        problem_id = str(payload.get("problem_id", ""))
        
        if problem_id:
            return f"dt:{problem_id}"
        elif project_id and mr_iid:
            return f"mr:{project_id}:{mr_iid}"
        else:
            return f"task:{task_id}"

    async def build_context(self, task_id: str, objective: str, payload: dict) -> AgentContext:
        cache_key = self._get_cache_key(task_id, payload)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        
        # Check TTL cache
        if cache_key in self._cache:
            expiry, cached_ctx = self._cache[cache_key]
            if now < expiry:
                print(f"[OK] [ContextBuilder] Returning cached AgentContext for key: {cache_key}")
                # Return updated context snapshot representing new task metadata
                return cached_ctx.update(task_id=task_id, objective=objective)
        
        print(f"[INFO] [ContextBuilder] Cache miss. Constructing new AgentContext asynchronously for: {cache_key}")
        
        # 1. Fetch Repository details
        project_id = str(payload.get("project", {}).get("id") or payload.get("project_id", "82576405"))
        repo_data = {}
        try:
            repo_data = await repository_service.get_repository(project_id)
        except Exception as e:
            print(f"[WARN] [ContextBuilder] Failed to fetch repository: {e}")
            
        repo_ctx = RepositoryContext(
            id=project_id,
            name=repo_data.get("name", payload.get("project", {}).get("path_with_namespace", "unknown").split("/")[-1]),
            git_url=repo_data.get("web_url", payload.get("project", {}).get("http_url", "")),
            visibility=repo_data.get("visibility", "private"),
            owner=repo_data.get("owner", "owner")
        )
        
        # 2. Fetch Branch details
        object_attrs = payload.get("object_attributes", {})
        branch_ctx = BranchContext(
            source_branch=object_attrs.get("source_branch", "main"),
            target_branch=object_attrs.get("target_branch", "main"),
            base_commit_sha=object_attrs.get("last_commit", {}).get("id", ""),
            head_commit_sha=object_attrs.get("sha", "")
        )
        
        # 3. Fetch User Context
        user_id = str(payload.get("user", {}).get("id") or object_attrs.get("author_id", "unknown"))
        user_data = {}
        try:
            user_data = await user_service.get_user(user_id)
        except Exception as e:
            print(f"[WARN] [ContextBuilder] Failed to fetch user: {e}")
            
        raw_perms = user_data.get("permissions", ["read"]) if user_data else ["read"]
        # Deduplicate and normalize permissions
        normalized_perms = sorted(list(set([str(p).lower().strip() for p in raw_perms])))
        
        user_ctx = UserContext(
            user_id=user_id,
            username=user_data.get("username", payload.get("user", {}).get("username", "unknown")) if user_data else "unknown",
            email=user_data.get("email", None) if user_data else None,
            permissions=normalized_perms
        )
        
        # 4. Fetch Schema Context
        db_name = "gatekeeper_dev"
        collections = []
        try:
            db = await mongo_client.get_database()
            collections = await db.list_collection_names()
        except Exception as e:
            print(f"[WARN] [ContextBuilder] Failed to query schema: {e}")
            
        schema_ctx = SchemaContext(
            db_name=db_name,
            collections=collections,
            last_schema_scan=now.isoformat()
        )
        
        # 5. Incident Context (if dynatrace alert)
        incident_ctx = None
        if "problem_id" in payload:
            incident_ctx = IncidentContext(
                problem_id=str(payload.get("problem_id", "")),
                title=payload.get("title", "Production Exception"),
                severity=payload.get("severity", "CRITICAL"),
                impacted_entity=payload.get("impacted_entity", "production-backend"),
                stack_trace=None
            )
            
        # 6. Deployment Context
        deploy_ctx = DeploymentContext(
            environment="production" if "problem_id" in payload else "development",
            cluster_name="k8s-prod-cluster" if "problem_id" in payload else "k8s-dev-cluster",
            active_version=object_attrs.get("sha", "v1.0.0")
        )
        
        # 7. Historical Context from MongoDB
        recent_tasks = []
        execution_count = 0
        try:
            traces = await mongo_client.find(
                collection_name="agent_execution_traces",
                filter={"repository_id": project_id},
                limit=5,
                sort=[("created_at", -1)]
            )
            recent_tasks = [t.get("task_id") for t in traces if "task_id" in t]
            db = await mongo_client.get_database()
            execution_count = await db["agent_execution_traces"].count_documents({"repository_id": project_id})
        except Exception as e:
            print(f"[WARN] [ContextBuilder] Failed to query historical memory: {e}")
            
        history_ctx = HistoricalMemoryContext(
            recent_tasks=recent_tasks,
            execution_traces_count=execution_count
        )
        
        # Build composite context
        context = AgentContext(
            version=1,
            task_id=task_id,
            objective=objective,
            created_at=now.isoformat(),
            repository=repo_ctx,
            branch=branch_ctx,
            user=user_ctx,
            schema_ctx=schema_ctx,
            incident=incident_ctx,
            deployment=deploy_ctx,
            history=history_ctx
        )
        
        # Save to cache with TTL
        expiry_time = now + datetime.timedelta(seconds=self.ttl)
        self._cache[cache_key] = (expiry_time, context)
        
        return context

    @classmethod
    def build_from_gitlab_mr(cls, payload: dict, repository_path: Optional[str] = None) -> AgentContext:
        object_attrs = payload.get("object_attributes", {})
        project_id = str(payload.get("project", {}).get("id") or payload.get("project_id", "82576405"))
        user_id = str(payload.get("user", {}).get("id") or object_attrs.get("author_id", "unknown"))
        mr_iid = str(object_attrs.get("iid", "unknown"))
        
        task_id = f"mr-review-{uuid.uuid4().hex[:8]}"
        objective = f"Perform GitLab Merge Request Review for MR {mr_iid}"
        
        repo_ctx = RepositoryContext(
            id=project_id,
            name=payload.get("project", {}).get("path_with_namespace", "unknown").split("/")[-1],
            git_url=payload.get("project", {}).get("http_url", ""),
            repo_path=repository_path
        )
        
        branch_ctx = BranchContext(
            source_branch=object_attrs.get("source_branch", "main"),
            target_branch=object_attrs.get("target_branch", "main"),
            base_commit_sha=object_attrs.get("last_commit", {}).get("id", ""),
            head_commit_sha=object_attrs.get("sha", "")
        )
        
        user_ctx = UserContext(
            user_id=user_id,
            username=payload.get("user", {}).get("username", "unknown"),
            permissions=["read", "write"]
        )
        
        schema_ctx = SchemaContext(
            db_name="gatekeeper_dev"
        )
        
        metadata = {
            "trigger_type": "gitlab_mr",
            "mr_iid": mr_iid,
            "project_id": project_id
        }
        
        return AgentContext(
            task_id=task_id,
            objective=objective,
            repository=repo_ctx,
            branch=branch_ctx,
            user=user_ctx,
            schema_ctx=schema_ctx,
            metadata=metadata
        )

    @classmethod
    def build_from_dynatrace_crash(cls, payload: dict, repository_path: Optional[str] = None, target_project_id: Optional[str] = None) -> AgentContext:
        problem_id = str(payload.get("problem_id", "unknown"))
        project_id = str(target_project_id or "82576405")
        
        task_id = f"remediation-{problem_id}-{uuid.uuid4().hex[:8]}"
        objective = f"Diagnose and automatically self-heal Dynatrace incident {problem_id}."
        
        repo_ctx = RepositoryContext(
            id=project_id,
            name="unknown-repo",
            repo_path=repository_path
        )
        
        branch_ctx = BranchContext(
            source_branch="main",
            target_branch="main"
        )
        
        user_ctx = UserContext(
            user_id="dynatrace-operator",
            username="dynatrace",
            permissions=["read", "write"]
        )
        
        schema_ctx = SchemaContext(
            db_name="gatekeeper_dev"
        )
        
        incident_ctx = IncidentContext(
            problem_id=problem_id,
            title=payload.get("title", "Production Crash"),
            severity=payload.get("severity", "CRITICAL"),
            impacted_entity=payload.get("impacted_entity", "production-backend")
        )
        
        metadata = {
            "trigger_type": "dynatrace_crash",
            "problem_id": problem_id,
            "severity": payload.get("severity", "CRITICAL")
        }
        
        return AgentContext(
            task_id=task_id,
            objective=objective,
            repository=repo_ctx,
            branch=branch_ctx,
            user=user_ctx,
            schema_ctx=schema_ctx,
            incident=incident_ctx,
            metadata=metadata
        )

    @staticmethod
    async def build_from_sentry_issue(payload: dict, repository_path: Optional[str] = None, target_project_id: Optional[str] = None, user_id: Optional[str] = None, username: Optional[str] = None) -> AgentContext:
        """Build AgentContext from Sentry webhook payload.

        Args:
            payload: Normalized Sentry webhook payload
            repository_path: Optional local path to repository
            target_project_id: Optional target project ID
            user_id: Optional user ID for GitLab operations (defaults to repository owner)
            username: Optional username for GitLab operations
        """
        from services import mongo_client

        issue_id = str(payload.get("issue_id", "unknown"))
        project_id = str(target_project_id or payload.get("tags", {}).get("gitlab.project_id", "82576405"))

        # Fetch repository from MongoDB to get the URL and other details
        repo_url = None
        repo_name = payload.get("project", "unknown")

        if project_id and project_id != "82576405":  # Not the default
            try:
                repo_doc = await mongo_client.find_one(
                    collection_name="connected_repositories",
                    filter={"id": project_id}
                )
                if repo_doc:
                    repo_url = repo_doc.get("url", "")
                    repo_name = repo_doc.get("name", repo_name)
                    print(f"[DEBUG] Found repository in MongoDB: {repo_name} ({project_id})", flush=True)
                else:
                    print(f"[WARN] Repository {project_id} not found in MongoDB", flush=True)
            except Exception as e:
                print(f"[WARN] Failed to fetch repository from MongoDB: {e}", flush=True)

        task_id = f"sentry-bug-{issue_id}-{uuid.uuid4().hex[:8]}"
        objective = f"Analyze and fix Sentry issue {issue_id}. Fetch issue details, identify root cause, and create a draft MR with the fix."

        repo_ctx = RepositoryContext(
            id=project_id,
            name=repo_name,
            git_url=repo_url,
            repo_path=repository_path
        )

        branch_ctx = BranchContext(
            source_branch="main",
            target_branch="main"
        )

        # Use provided user credentials or fallback to sentry-operator
        user_ctx = UserContext(
            user_id=user_id or "sentry-operator",
            username=username or "sentry",
            permissions=["read", "write"]
        )

        schema_ctx = SchemaContext(
            db_name="gatekeeper_dev"
        )

        sentry_ctx = SentryIssueContext(
            issue_id=issue_id,
            title=payload.get("title", ""),
            level=str(payload.get("level", "")),
            environment=str(payload.get("environment", "")),
            culprit=payload.get("culprit"),
            stack_trace=payload.get("message", ""),
            git_commit_sha=payload.get("tags", {}).get("sentry.sha")
        )

        metadata = {
            "trigger_type": "sentry_issue",
            "issue_id": issue_id,
            "severity": str(payload.get("level", ""))
        }

        return AgentContext(
            task_id=task_id,
            objective=objective,
            repository=repo_ctx,
            branch=branch_ctx,
            user=user_ctx,
            schema_ctx=schema_ctx,
            sentry_issue=sentry_ctx,
            metadata=metadata
        )

