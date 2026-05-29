"""
Repository service for Gatekeeper.

Handles repository management, merge request tracking, and policy enforcement.
Integrates with GitLab MCP to fetch repository data and manage integrations.
"""

import os
import json
import httpx
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from enum import Enum

from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

# Import MCP services
from services import mcp_service
from services import auth_service
from services import mongo_client

# GitLab configuration
GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
GITLAB_PERSONAL_ACCESS_TOKEN = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")

# MongoDB configuration check
MONGO_CONNECTION_STRING = os.getenv("MDB_MCP_CONNECTION_STRING", "")
if not MONGO_CONNECTION_STRING:
    print("[⚠️] MDB_MCP_CONNECTION_STRING not set in environment variables")
    print("[ℹ️] Repository data will be stored in memory only")
    print("[ℹ️] To enable MongoDB storage, set MDB_MCP_CONNECTION_STRING in .env file")
else:
    print(f"[✅] MongoDB connection string configured: {MONGO_CONNECTION_STRING[:20]}...{MONGO_CONNECTION_STRING[-10:]}")


# ============================================================================
# Enums
# ============================================================================

async def _fetch_gitlab_projects_direct(token: Optional[str] = None) -> List[Dict]:
    """
    Fetch projects directly from GitLab API using httpx.
    Fallback method if MCP is not available.

    Args:
        token: Optional GitLab access token (uses env var if not provided)

    Returns:
        List of GitLab projects
    """
    # Use provided token or fall back to env var
    access_token = token or GITLAB_PERSONAL_ACCESS_TOKEN

    if not access_token:
        print("[WARN] No GitLab access token available")
        return []

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITLAB_BASE_URL}/api/v4/projects",
                headers=headers,
                params={"membership": True, "per_page": 50, "simple": False},
                timeout=30.0
            )
            response.raise_for_status()
            projects = response.json()
            print(f"[INFO] Fetched {len(projects)} projects from GitLab API directly")
            return projects
    except Exception as e:
        print(f"[ERROR] Failed to fetch from GitLab API: {e}")
        return []


# ============================================================================
# Enums
# ============================================================================

class RepositoryVisibility(str, Enum):
    """Repository visibility levels."""
    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class RepositoryStatus(str, Enum):
    """Repository sync status."""
    ACTIVE = "active"
    SYNCING = "syncing"
    ERROR = "error"
    PENDING = "pending"


class MRStatus(str, Enum):
    """Merge request status."""
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"


# ============================================================================
# MongoDB Storage
# ============================================================================

DB_NAME = "gatekeeper"
REPOS_COLLECTION = "connected_repositories"
MRS_COLLECTION = "merge_requests"
POLICIES_COLLECTION = "repository_policies"

# In-memory cache (fallback when MongoDB is not available)
_repositories: Dict[str, Dict] = {}
_merge_requests: Dict[str, List[Dict]] = {}
_policies: Dict[str, List[Dict]] = {}


async def list_mongodb_tools() -> List[str]:
    """
    List available MongoDB operations (using direct Motor client).

    Returns:
        List of operation names
    """
    return ["insert_one", "find_one", "find", "update_one", "delete_one", "list_collections"]


async def test_mongodb_connection() -> Dict:
    """
    Test MongoDB connection and return connection status.

    Returns:
        Dict with connection status and error details if any
    """
    # Check connection string
    if not MONGO_CONNECTION_STRING:
        return {
            "connected": False,
            "error": "MDB_MCP_CONNECTION_STRING not set",
            "details": "Set MDB_MCP_CONNECTION_STRING in .env file",
            "example": "MDB_MCP_CONNECTION_STRING=mongodb+srv://username:password@cluster.mongodb.net/?appName=Cluster0"
        }

    # Test connection using direct MongoDB client
    result = await mongo_client.test_connection()

    # Add MCP service status to the result
    result["mongo_session"] = bool(mcp_service.mongo_session)
    result["gitlab_session"] = bool(mcp_service.gitlab_session)

    return result


async def _store_repository(user_id: str, repo_data: Dict):
    """Store a connected repository in MongoDB."""
    try:
        # Check if already exists
        existing = await _find_repository(user_id, repo_data["id"])
        if existing:
            print(f"[INFO] Repository {repo_data['name']} already connected")
            return

        # Add user_id and timestamp
        repo_data["user_id"] = user_id
        repo_data["connected_at"] = datetime.now().isoformat()

        # Store in MongoDB using direct Motor client
        if MONGO_CONNECTION_STRING:
            print(f"[INFO] Attempting to store repository {repo_data['name']} in MongoDB...")
            print(f"[INFO] Database: {DB_NAME}, Collection: {REPOS_COLLECTION}")

            try:
                # Use direct MongoDB client (Motor)
                doc_id = await mongo_client.insert_one(
                    collection_name=REPOS_COLLECTION,
                    document=repo_data
                )
                print(f"[✅] Successfully stored repository {repo_data['name']} in MongoDB with ID: {doc_id}")
            except Exception as mongo_err:
                print(f"[⚠️] MongoDB insert failed: {mongo_err}")
                print(f"[ℹ️] Falling back to in-memory storage for repository {repo_data['name']}")
                # Store in memory as fallback
                _repositories[repo_data["id"]] = repo_data
        else:
            print(f"[⚠️] MongoDB connection string not configured - repository {repo_data['name']} stored in memory only")
            print(f"[ℹ️] Set MDB_MCP_CONNECTION_STRING in .env to enable MongoDB storage")

            # Store in memory as fallback
            _repositories[repo_data["id"]] = repo_data
            print(f"[✅] Repository {repo_data['name']} stored in in-memory cache")
    except Exception as e:
        print(f"[❌] Failed to store repository: {e}")
        print(f"[ℹ️] Repository data: {repo_data.get('name', 'unknown')}")
        import traceback
        traceback.print_exc()

        # Fallback to in-memory storage
        _repositories[repo_data["id"]] = repo_data
        print(f"[ℹ️] Repository stored in in-memory cache as fallback")


async def _find_repository(user_id: str, repo_id: str) -> Optional[Dict]:
    """Find a repository by user_id and repo_id."""
    try:
        if MONGO_CONNECTION_STRING:
            document = await mongo_client.find_one(
                collection_name=REPOS_COLLECTION,
                filter={"user_id": user_id, "id": repo_id}
            )
            return document
    except Exception as e:
        print(f"[ERROR] Failed to find repository: {e}")
    return None


async def _get_user_repositories(user_id: str, limit: Optional[int] = None) -> List[Dict]:
    """Get all repositories connected by a user."""
    try:
        if MONGO_CONNECTION_STRING:
            documents = await mongo_client.find(
                collection_name=REPOS_COLLECTION,
                filter={"user_id": user_id},
                limit=limit
            )
            print(f"[INFO] Retrieved {len(documents)} repositories from MongoDB for user {user_id}")
            return documents
        else:
            print(f"[⚠️] MongoDB connection string not configured - using in-memory cache for user {user_id}")
    except Exception as e:
        print(f"[ERROR] Failed to get user repositories from MongoDB: {e}")
        print(f"[ℹ️] Falling back to in-memory cache")

    # Fallback to in-memory cache
    print(f"[INFO] Returning repositories from in-memory cache")
    repos = list(_repositories.values())
    if limit and limit > 0:
        repos = repos[:limit]
    return repos


# ============================================================================
# Repository Operations
# ============================================================================

async def get_all_repositories(user_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
    """
    Get all connected repositories for a user from MongoDB.

    Args:
        user_id: Optional user ID to get their repositories
        limit: Optional limit on number of repositories to return

    Returns:
        List of repositories with their current status
    """
    repos = []

    # If user_id provided, fetch their repositories from MongoDB
    if user_id:
        try:
            user_repos = await _get_user_repositories(user_id, limit)

            if user_repos:
                # Update in-memory cache
                _repositories.clear()
                for repo in user_repos:
                    repo_id = repo.get("id", "")
                    _repositories[repo_id] = repo

                # Format for response
                for repo in user_repos:
                    repos.append({
                        "id": repo.get("id", ""),
                        "name": repo.get("name", ""),
                        "full_name": repo.get("full_name", ""),
                        "visibility": repo.get("visibility", ""),
                        "url": repo.get("url", ""),
                        "last_sync": repo.get("last_sync", datetime.now().isoformat()),
                        "health_score": repo.get("health_score", 100.0),
                        "status": repo.get("status", "active"),
                        "description": repo.get("description", ""),
                        "created_at": repo.get("created_at", datetime.now().isoformat()),
                        "executive_summary": repo.get("executive_summary", ""),
                        "vector_analysis": repo.get("vector_analysis", {})
                    })

                print(f"[INFO] Loaded {len(repos)} repositories from MongoDB for user {user_id}")
                return repos
        except Exception as e:
            print(f"[ERROR] Failed to fetch user repositories from MongoDB: {e}")

    # Fallback to in-memory repositories (for development/testing)
    print("[INFO] Using in-memory repository cache")
    for repo_id, repo_data in _repositories.items():
        repos.append({
            "id": repo_data["id"],
            "name": repo_data["name"],
            "full_name": repo_data["full_name"],
            "visibility": repo_data["visibility"].value,
            "url": repo_data["url"],
            "last_sync": repo_data["last_sync"].isoformat(),
            "health_score": repo_data["health_score"],
            "status": repo_data["status"].value,
            "description": repo_data.get("description"),
            "created_at": repo_data["created_at"].isoformat(),
            "executive_summary": repo_data.get("executive_summary", ""),
            "vector_analysis": repo_data.get("vector_analysis", {})
        })

    return repos

    # Return formatted repositories
    repos = []
    for repo_id, repo_data in _repositories.items():
        # Format for response
        repo = {
            "id": repo_data["id"],
            "name": repo_data["name"],
            "full_name": repo_data["full_name"],
            "visibility": repo_data["visibility"].value,
            "url": repo_data["url"],
            "last_sync": repo_data["last_sync"].isoformat(),
            "health_score": repo_data["health_score"],
            "status": repo_data["status"].value,
            "description": repo_data.get("description"),
            "created_at": repo_data["created_at"].isoformat(),
            "executive_summary": repo_data.get("executive_summary", ""),
            "vector_analysis": repo_data.get("vector_analysis", {})
        }
        repos.append(repo)

    return repos


def _map_gitlab_visibility(gitlab_visibility: str) -> RepositoryVisibility:
    """Map GitLab visibility to our enum."""
    visibility_map = {
        "public": RepositoryVisibility.PUBLIC,
        "private": RepositoryVisibility.PRIVATE,
        "internal": RepositoryVisibility.INTERNAL
    }
    return visibility_map.get(gitlab_visibility.lower(), RepositoryVisibility.PRIVATE)


def _get_enum_value(enum_or_string) -> str:
    """Safely get the string value from an enum or return the string directly."""
    if hasattr(enum_or_string, 'value'):
        return enum_or_string.value
    return enum_or_string


async def get_repository_avg_review_time(repo_id: str) -> float:
    """
    Get the pre-calculated average review time from repository document.

    Args:
        repo_id: Repository ID

    Returns:
        Average review time in minutes, or 2.5 if not set
    """
    try:
        if MONGO_CONNECTION_STRING:
            repo = await mongo_client.find_one(
                collection_name=REPOS_COLLECTION,
                filter={"id": repo_id},
                projection={"avg_review_time": 1}
            )
            if repo and "avg_review_time" in repo:
                return repo["avg_review_time"]
        return 2.5
    except Exception as e:
        print(f"[ERROR] Failed to get avg review time: {e}")
        return 2.5


async def update_repository_avg_review_time(repo_id: str, new_duration_seconds: int) -> bool:
    """
    Update the running average review time in repository document when an MR completes.

    Uses running average formula: new_avg = ((old_avg * n) + new_value) / (n + 1)

    Args:
        repo_id: Repository ID
        new_duration_seconds: Duration of the just-completed MR review in seconds

    Returns:
        True if update successful, False otherwise
    """
    try:
        if not MONGO_CONNECTION_STRING:
            return False

        # Get current repository data
        repo = await mongo_client.find_one(
            collection_name=REPOS_COLLECTION,
            filter={"id": repo_id},
            projection={"avg_review_time": 1, "mrs_reviewed": 1}
        )

        if not repo:
            print(f"[WARN] Repository {repo_id} not found for avg review time update")
            return False

        # Get current values (with defaults)
        current_avg_minutes = repo.get("avg_review_time", 2.5)
        current_mrs_count = repo.get("mrs_reviewed", 0)

        # Calculate new running average
        # Convert current avg from minutes to seconds for calculation
        current_avg_seconds = current_avg_minutes * 60.0
        total_seconds = (current_avg_seconds * current_mrs_count) + new_duration_seconds
        new_avg_seconds = total_seconds / (current_mrs_count + 1)
        new_avg_minutes = round(new_avg_seconds / 60.0, 2)

        # Update repository document
        await mongo_client.update_one(
            collection_name=REPOS_COLLECTION,
            filter={"id": repo_id},
            update={
                "$set": {"avg_review_time": new_avg_minutes},
                "$inc": {"mrs_reviewed": 1}
            }
        )

        print(f"[INFO] Updated avg review time for repo {repo_id}: {new_avg_minutes} minutes (MRs reviewed: {current_mrs_count + 1})")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to update avg review time: {e}")
        return False


async def get_repository(repo_id: str) -> Dict:
    """
    Get detailed information about a specific repository.

    Args:
        repo_id: Repository ID

    Returns:
        Detailed repository information

    Raises:
        HTTPException: If repository not found
    """
    # Try to fetch from MongoDB first (for connected repos)
    try:
        if MONGO_CONNECTION_STRING:
            mongo_repo = await mongo_client.find_one(
                collection_name=REPOS_COLLECTION,
                filter={"id": repo_id}
            )
            if mongo_repo:
                print(f"[INFO] Found repository {repo_id} in MongoDB")
                # Parse last_sync if it's a string
                last_sync = mongo_repo.get("last_sync", datetime.now())
                if isinstance(last_sync, str):
                    try:
                        last_sync = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                    except:
                        last_sync = datetime.now()

                # Parse created_at if it's a string
                created_at = mongo_repo.get("created_at", datetime.now())
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    except:
                        created_at = datetime.now()

                mr_count = len(_merge_requests.get(repo_id, []))
                avg_time = await get_repository_avg_review_time(repo_id)

                return {
                    "id": mongo_repo.get("id", repo_id),
                    "name": mongo_repo.get("name", "Unknown"),
                    "full_name": mongo_repo.get("full_name", ""),
                    "visibility": _get_enum_value(mongo_repo.get("visibility", "private")),
                    "url": mongo_repo.get("url", ""),
                    "last_sync": last_sync.isoformat() if hasattr(last_sync, 'isoformat') else str(last_sync),
                    "health_score": mongo_repo.get("health_score", 100.0),
                    "status": _get_enum_value(mongo_repo.get("status", "active")),
                    "description": mongo_repo.get("description", ""),
                    "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at),
                    "executive_summary": mongo_repo.get("executive_summary", ""),
                    "vector_analysis": mongo_repo.get("vector_analysis", {}),
                    "stats": {
                        "mrs_reviewed": mr_count,
                        "avg_review_time": avg_time,
                        "auto_fixes_applied": mongo_repo.get("auto_fixes_applied", 0),
                        "test_coverage": mongo_repo.get("test_coverage", "0%")
                    },
                    # Credential status fields (don't return actual values, just indicate presence)
                    "mongodb_uri": mongo_repo.get("mongodb_uri", ""),
                    "fivetran_api_key": mongo_repo.get("fivetran_api_key", ""),
                    "fivetran_api_secret": mongo_repo.get("fivetran_api_secret", ""),
                    "credentials_encrypted": mongo_repo.get("credentials_encrypted", False)
                }
    except Exception as e:
        print(f"[ERROR] Failed to fetch repository from MongoDB: {e}")

    # Try to fetch fresh data from GitLab MCP
    if mcp_service.gitlab_session and repo_id not in _repositories:
        try:
            print(f"[INFO] Fetching repository {repo_id} from GitLab...")
            # Extract numeric project ID for GitLab API
            try:
                project_id = int(repo_id)
            except ValueError:
                project_id = repo_id

            # Call GitLab MCP to get project
            result = await mcp_service.gitlab_session.call_tool(
                name="get_project",
                arguments={"project_id": project_id}
            )

            if result and hasattr(result, 'content') and result.content:
                project = json.loads(result.content[0].text)

                # Add to repositories
                _repositories[repo_id] = {
                    "id": repo_id,
                    "name": project.get("name", "Unknown"),
                    "full_name": project.get("path_with_namespace", ""),
                    "visibility": _map_gitlab_visibility(project.get("visibility", "private")),
                    "url": project.get("web_url", ""),
                    "last_sync": datetime.now(),
                    "health_score": 100.0,
                    "status": RepositoryStatus.ACTIVE,
                    "description": project.get("description", ""),
                    "created_at": datetime.fromisoformat(project.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")),
                    "executive_summary": "Repository imported from GitLab.",
                    "vector_analysis": {
                        "security": "0.0%",
                        "performance": "0.0%",
                        "complexity": "0.0%"
                    }
                }
                print(f"[INFO] Fetched repository {repo_id} from GitLab")

        except Exception as e:
            print(f"[ERROR] Failed to fetch repository from GitLab MCP: {e}")

    if repo_id not in _repositories:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repo_id} not found"
        )

    repo_data = _repositories[repo_id]

    # Get MR count
    mr_count = len(_merge_requests.get(repo_id, []))
    avg_time = await get_repository_avg_review_time(repo_id)

    return {
        "id": repo_data["id"],
        "name": repo_data["name"],
        "full_name": repo_data["full_name"],
        "visibility": _get_enum_value(repo_data["visibility"]),
        "url": repo_data["url"],
        "last_sync": repo_data["last_sync"].isoformat() if hasattr(repo_data["last_sync"], 'isoformat') else str(repo_data["last_sync"]),
        "health_score": repo_data["health_score"],
        "status": _get_enum_value(repo_data["status"]),
        "description": repo_data.get("description"),
        "created_at": repo_data["created_at"].isoformat() if hasattr(repo_data["created_at"], 'isoformat') else str(repo_data["created_at"]),
        "executive_summary": repo_data.get("executive_summary", ""),
        "vector_analysis": repo_data.get("vector_analysis", {}),
        "stats": {
            "mrs_reviewed": mr_count,
            "avg_review_time": avg_time,
            "auto_fixes_applied": 12,
            "test_coverage": 87.3
        },
        # Credential status fields (default empty for in-memory repos)
        "mongodb_uri": repo_data.get("mongodb_uri", ""),
        "fivetran_api_key": repo_data.get("fivetran_api_key", ""),
        "fivetran_api_secret": repo_data.get("fivetran_api_secret", ""),
        "credentials_encrypted": repo_data.get("credentials_encrypted", False)
    }


async def get_repository_mrs(repo_id: str, limit: int = 50) -> List[Dict]:
    """
    Get merge requests for a repository from GitLab.

    Args:
        repo_id: Repository ID
        limit: Maximum number of MRs to return

    Returns:
        List of merge requests

    Raises:
        HTTPException: If repository not found
    """
    if repo_id not in _repositories:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repo_id} not found"
        )

    # Try to fetch from GitLab MCP if available
    if mcp_service.gitlab_session:
        try:
            print(f"[INFO] Fetching MRs for repo {repo_id} from GitLab...")
            repo_data = _repositories.get(repo_id, {})
            # Extract numeric project ID for GitLab API
            try:
                project_id = int(repo_id)
            except ValueError:
                project_id = repo_id

            # Call GitLab MCP to list MRs
            result = await mcp_service.gitlab_session.call_tool(
                name="list_merge_requests",
                arguments={"project_id": project_id, "state": "opened", "per_page": limit}
            )

            if result and hasattr(result, 'content') and result.content:
                mrs_data = json.loads(result.content[0].text)

                # Update cached MRs
                _merge_requests[repo_id] = []
                for mr in mrs_data:
                    _merge_requests[repo_id].append({
                        "id": mr.get("id", ""),
                        "iid": mr.get("iid", 0),
                        "title": mr.get("title", ""),
                        "repository_id": repo_id,
                        "repository_name": repo_data.get("name", ""),
                        "status": _map_gitlab_mr_state(mr.get("state", "opened")),
                        "author": mr.get("author", {}).get("username", "") if isinstance(mr.get("author"), dict) else mr.get("author", ""),
                        "created_at": datetime.fromisoformat(mr.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")),
                        "updated_at": datetime.fromisoformat(mr.get("updated_at", datetime.now().isoformat()).replace("Z", "+00:00")),
                        "web_url": mr.get("web_url", ""),
                        "ai_summary": "Pending AI analysis...",
                        "health_score": None
                    })

                print(f"[INFO] Fetched {len(_merge_requests[repo_id])} MRs from GitLab")

        except Exception as e:
            print(f"[ERROR] Failed to fetch MRs from GitLab MCP: {e}")
            # Continue with cached data

    mrs = _merge_requests.get(repo_id, [])

    # Format for response
    result = []
    for mr in mrs[:limit]:
        result.append({
            "id": mr["id"],
            "iid": mr["iid"],
            "title": mr["title"],
            "repository_id": mr["repository_id"],
            "repository_name": mr["repository_name"],
            "status": mr["status"].value,
            "author": mr["author"],
            "created_at": mr["created_at"].isoformat(),
            "updated_at": mr.get("updated_at", mr["created_at"]).isoformat(),
            "web_url": mr["web_url"],
            "ai_summary": mr.get("ai_summary"),
            "health_score": mr.get("health_score")
        })

    return result


def _map_gitlab_mr_state(state: str) -> MRStatus:
    """Map GitLab MR state to our enum."""
    state_map = {
        "opened": MRStatus.OPEN,
        "closed": MRStatus.CLOSED,
        "merged": MRStatus.MERGED,
        "draft": MRStatus.DRAFT
    }
    return state_map.get(state.lower(), MRStatus.OPEN)


def get_repository_policies(repo_id: str) -> List[Dict]:
    """
    Get active policies for a repository.

    Args:
        repo_id: Repository ID

    Returns:
        List of active policies

    Raises:
        HTTPException: If repository not found
    """
    if repo_id not in _repositories:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repo_id} not found"
        )

    policies = _policies.get(repo_id, [])

    # Format for response
    result = []
    for policy in policies:
        result.append({
            "id": policy["id"],
            "name": policy["name"],
            "type": policy["type"],
            "enabled": policy["enabled"],
            "description": policy["description"]
        })

    return result


def search_repositories(query: str) -> List[Dict]:
    """
    Search repositories by name or description.

    Args:
        query: Search query string

    Returns:
        List of matching repositories
    """
    query_lower = query.lower()
    results = []

    for repo_id, repo_data in _repositories.items():
        # Search in name and description
        name_match = query_lower in repo_data["name"].lower()
        desc_match = query_lower in repo_data.get("description", "").lower()

        if name_match or desc_match:
            results.append({
                "id": repo_data["id"],
                "name": repo_data["name"],
                "full_name": repo_data["full_name"],
                "visibility": repo_data["visibility"].value,
                "url": repo_data["url"],
                "last_sync": repo_data["last_sync"].isoformat(),
                "health_score": repo_data["health_score"],
                "status": repo_data["status"].value
            })

    return results


async def import_repository(gitlab_path: str, user_id: Optional[str] = None) -> Dict:
    """
    Import a new GitLab repository.

    Args:
        gitlab_path: GitLab project path (e.g., "group/project")
        user_id: Optional user ID requesting the import

    Returns:
        Imported repository information

    Raises:
        HTTPException: If import fails
    """
    # Check if already exists for this user
    if user_id:
        existing_repos = await _get_user_repositories(user_id)
        for repo in existing_repos:
            if gitlab_path in repo.get("full_name", ""):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Repository {gitlab_path} is already connected"
                )

    # Generate new ID
    new_id = str(len(_repositories) + 1)

    # Create repository entry
    new_repo = {
        "id": new_id,
        "name": gitlab_path.split("/")[-1] if "/" in gitlab_path else gitlab_path,
        "full_name": gitlab_path,
        "visibility": RepositoryVisibility.PRIVATE,
        "url": f"https://gitlab.com/{gitlab_path}",
        "last_sync": datetime.now(),
        "health_score": 100.0,
        "status": RepositoryStatus.SYNCING,
        "description": f"Imported from {gitlab_path}",
        "created_at": datetime.now(),
        "executive_summary": "Repository imported. Initial analysis in progress...",
        "vector_analysis": {
            "security": "0.0%",
            "performance": "0.0%",
            "complexity": "0.0%"
        }
    }

    _repositories[new_id] = new_repo
    _merge_requests[new_id] = []
    _policies[new_id] = []

    # Store in MongoDB if user_id provided
    if user_id:
        await _store_repository(user_id, new_repo)

    return {
        "id": new_repo["id"],
        "name": new_repo["name"],
        "full_name": new_repo["full_name"],
        "visibility": new_repo["visibility"].value,
        "url": new_repo["url"],
        "status": new_repo["status"].value,
        "message": "Repository import started successfully"
    }


async def get_available_gitlab_repositories(user_id: str, search_query: str = "") -> List[Dict]:
    """
    Get user's GitLab repositories that are not yet connected.

    Args:
        user_id: User ID to get their GitLab token and filter connected repos
        search_query: Optional search query to filter repositories

    Returns:
        List of available GitLab repositories
    """
    # Get user's GitLab token
    gitlab_token = None
    user_session = auth_service.get_user_session(user_id)
    if user_session:
        gitlab_token = user_session.get("gitlab_access_token")

    if not gitlab_token:
        gitlab_token = GITLAB_PERSONAL_ACCESS_TOKEN

    if not gitlab_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No GitLab access token available. Please login or configure GITLAB_PERSONAL_ACCESS_TOKEN"
        )

    # Get user's connected repositories
    connected_repo_ids = set()
    user_repos = await _get_user_repositories(user_id)
    for repo in user_repos:
        connected_repo_ids.add(str(repo.get("id", "")))

    # Fetch all user's GitLab repositories
    headers = {"Authorization": f"Bearer {gitlab_token}"}
    params = {"membership": True, "per_page": 100}

    if search_query:
        params["search"] = search_query

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITLAB_BASE_URL}/api/v4/projects",
                headers=headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            all_projects = response.json()

            # Filter out already connected repositories
            available_repos = []
            for project in all_projects:
                repo_id = str(project.get("id", ""))
                if repo_id not in connected_repo_ids:
                    available_repos.append({
                        "id": repo_id,
                        "name": project.get("name", ""),
                        "full_name": project.get("path_with_namespace", ""),
                        "description": project.get("description", ""),
                        "visibility": _map_gitlab_visibility(project.get("visibility", "private")),
                        "url": project.get("web_url", ""),
                        "avatar_url": project.get("avatar_url"),
                        "last_activity": project.get("last_activity_at"),
                        "star_count": project.get("star_count", 0),
                        "forks_count": project.get("forks_count", 0)
                    })

            return available_repos

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitLab token expired or invalid. Please login again."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch GitLab repositories: {e.response.text}"
        )
    except Exception as e:
        print(f"[ERROR] Failed to fetch GitLab repositories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


async def connect_repository(user_id: str, repo_id: str) -> Dict:
    """
    Connect a GitLab repository and store it in MongoDB.

    Args:
        user_id: User ID connecting the repository
        repo_id: GitLab project ID

    Returns:
        Connected repository information
    """
    # Get user's GitLab token
    gitlab_token = None
    user_session = auth_service.get_user_session(user_id)
    if user_session:
        gitlab_token = user_session.get("gitlab_access_token")

    if not gitlab_token:
        gitlab_token = GITLAB_PERSONAL_ACCESS_TOKEN

    # Check if already connected
    existing = await _find_repository(user_id, repo_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository is already connected"
        )

    # Fetch repository details from GitLab
    headers = {"Authorization": f"Bearer {gitlab_token}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITLAB_BASE_URL}/api/v4/projects/{repo_id}",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            project = response.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found or you don't have access"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch repository: {e.response.text}"
        )

    # Create repository entry
    new_repo = {
        "id": str(project.get("id", "")),
        "name": project.get("name", ""),
        "full_name": project.get("path_with_namespace", ""),
        "visibility": _map_gitlab_visibility(project.get("visibility", "private")),
        "url": project.get("web_url", ""),
        "last_sync": datetime.now(),
        "health_score": 100.0,
        "status": RepositoryStatus.ACTIVE,
        "description": project.get("description", ""),
        "created_at": datetime.fromisoformat(project.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")),
        "avatar_url": project.get("avatar_url"),
        "executive_summary": "Repository connected. Initial analysis in progress...",
        "vector_analysis": {
            "security": "0.0%",
            "performance": "0.0%",
            "complexity": "0.0%"
        },
        "avg_review_time": 2.5,
        "mrs_reviewed": 0
    }

    # Store in memory
    _repositories[new_repo["id"]] = new_repo
    _merge_requests[new_repo["id"]] = []
    _policies[new_repo["id"]] = []

    # Store in MongoDB
    await _store_repository(user_id, new_repo)

    return {
        "id": new_repo["id"],
        "name": new_repo["name"],
        "full_name": new_repo["full_name"],
        "visibility": new_repo["visibility"].value,
        "url": new_repo["url"],
        "status": new_repo["status"].value,
        "message": "Repository connected successfully"
    }


async def disconnect_repository(user_id: str, repo_id: str) -> Dict:
    """
    Disconnect a repository and remove it from MongoDB.

    Args:
        user_id: User ID disconnecting the repository
        repo_id: Repository ID to disconnect

    Returns:
        Disconnection confirmation
    """
    try:
        if MONGO_CONNECTION_STRING:
            deleted = await mongo_client.delete_one(
                collection_name=REPOS_COLLECTION,
                filter={"user_id": user_id, "id": repo_id}
            )
            if deleted:
                print(f"[INFO] Disconnected repository {repo_id} for user {user_id} from MongoDB")
            else:
                print(f"[ℹ️] Repository {repo_id} not found in MongoDB for user {user_id}")

        # Remove from memory
        if repo_id in _repositories:
            del _repositories[repo_id]
        if repo_id in _merge_requests:
            del _merge_requests[repo_id]
        if repo_id in _policies:
            del _policies[repo_id]

        return {"message": "Repository disconnected successfully"}

    except Exception as e:
        print(f"[ERROR] Failed to disconnect repository: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def get_repository_summary(repo_id: str) -> Dict:
    """
    Get executive summary for a repository.

    Args:
        repo_id: Repository ID

    Returns:
        Repository summary with vector analysis

    Raises:
        HTTPException: If repository not found
    """
    repo = get_repository(repo_id)

    return {
        "repository_id": repo["id"],
        "repository_name": repo["name"],
        "executive_summary": repo.get("executive_summary", ""),
        "vector_analysis": repo.get("vector_analysis", {}),
        "health_score": repo.get("health_score", 0),
        "last_updated": repo.get("last_sync", "")
    }


# ============================================================================
# MongoDB MR Storage and Retrieval
# ============================================================================

def _relative_time(timestamp: str) -> str:
    """
    Convert timestamp to relative time string.

    Args:
        timestamp: ISO format timestamp

    Returns:
        Relative time string (e.g., "5m ago", "2h ago", "Yesterday")
    """
    try:
        from datetime import datetime, timezone

        # Parse timestamp
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            dt = timestamp

        # Make timezone-aware if naive
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - dt

        seconds = diff.total_seconds()

        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        elif seconds < 172800:
            return "Yesterday"
        else:
            days = int(seconds / 86400)
            return f"{days} days ago"
    except Exception as e:
        print(f"[ERROR] Failed to parse timestamp: {e}")
        return "Unknown"


async def store_mr_in_mongodb(mr_data: Dict) -> str:
    """
    Store a merge request in MongoDB.

    Args:
        mr_data: MR data dictionary from webhook

    Returns:
        MongoDB document ID

    Raises:
        Exception: If storage fails
    """
    try:
        if not MONGO_CONNECTION_STRING:
            print("[⚠️] MongoDB connection string not configured - MR stored in memory only")
            # Store in in-memory cache as fallback
            repo_id = mr_data.get("repository_id")
            if repo_id not in _merge_requests:
                _merge_requests[repo_id] = []
            _merge_requests[repo_id].append(mr_data)
            return "memory_" + str(len(_merge_requests[repo_id]))

        # Check if MR already exists
        existing = await mongo_client.find_one(
            collection_name=MRS_COLLECTION,
            filter={
                "repository_id": mr_data.get("repository_id"),
                "gitlab_mr_id": mr_data.get("gitlab_mr_id")
            }
        )

        if existing:
            # Update existing MR
            await mongo_client.update_one(
                collection_name=MRS_COLLECTION,
                filter={"_id": existing["_id"]},
                update={"$set": mr_data}
            )
            print(f"[INFO] Updated MR {mr_data.get('gitlab_mr_id')} in MongoDB")
            return str(existing["_id"])
        else:
            # Insert new MR
            doc_id = await mongo_client.insert_one(
                collection_name=MRS_COLLECTION,
                document=mr_data
            )
            print(f"[✅] Stored MR {mr_data.get('gitlab_mr_id')} in MongoDB with ID: {doc_id}")
            return doc_id

    except Exception as e:
        print(f"[❌] Failed to store MR in MongoDB: {e}")
        # Fallback to in-memory storage
        repo_id = mr_data.get("repository_id")
        if repo_id not in _merge_requests:
            _merge_requests[repo_id] = []
        _merge_requests[repo_id].append(mr_data)
        raise


async def get_repository_mrs_from_db(
    repo_id: str,
    limit: int = 50,
    status_filter: Optional[str] = None
) -> List[Dict]:
    """
    Get merge requests for a repository from MongoDB.

    Args:
        repo_id: Repository ID
        limit: Maximum number of MRs to return
        status_filter: Optional status filter (open, closed, merged, draft)

    Returns:
        List of merge requests with AI analysis and auto-fix data

    Raises:
        HTTPException: If repository not found
    """
    try:
        filter_query = {"repository_id": repo_id}

        if status_filter:
            filter_query["status"] = status_filter

        print(f"[DEBUG] Fetching MRs for repo_id: {repo_id} with filter: {filter_query}")

        # Fetch from MongoDB
        if MONGO_CONNECTION_STRING:
            documents = await mongo_client.find(
                collection_name=MRS_COLLECTION,
                filter=filter_query,
                limit=limit,
                sort=[("created_at", -1)]  # Newest first
            )
            print(f"[INFO] Fetched {len(documents)} MRs from MongoDB for repo {repo_id}")
            if len(documents) == 0:
                print(f"[DEBUG] No MRs found. Checking collection...")
                # Try to find any MRs in the collection for debugging
                all_mrs = await mongo_client.find(
                    collection_name=MRS_COLLECTION,
                    filter={},
                    limit=5
                )
                print(f"[DEBUG] Sample MRs in collection: {[mr.get('repository_id', 'no_repo_id') for mr in all_mrs]}")
        else:
            # Fallback to in-memory cache
            print(f"[⚠️] MongoDB not configured - using in-memory MR cache")
            documents = _merge_requests.get(repo_id, [])

        # Format for frontend response
        result = []
        for doc in documents:
            # Handle both MongoDB documents (with _id) and in-memory dicts
            if isinstance(doc, dict) and "_id" in doc:
                doc_id = str(doc["_id"])
            else:
                doc_id = doc.get("id", "")

            # Get changes data
            changes = doc.get("changes", {})
            if isinstance(changes, dict):
                additions = changes.get("additions", 0)
                deletions = changes.get("deletions", 0)
                files_changed = changes.get("files_changed", 0)
            else:
                additions = 0
                deletions = 0
                files_changed = 0

            result.append({
                "id": f"#{doc.get('gitlab_mr_id', doc.get('iid', ''))}",
                "gitlab_mr_id": doc.get("gitlab_mr_id", doc.get("iid")),
                "iid": doc.get("gitlab_mr_id", doc.get("iid")),
                "title": doc.get("title", ""),
                "repository_id": doc.get("repository_id", repo_id),
                "repository_name": doc.get("repository_name", ""),
                "status": doc.get("status", "open"),
                "author": doc.get("author", ""),
                "branch": doc.get("source_branch", ""),
                "target": doc.get("target_branch", "main"),
                "web_url": doc.get("web_url", ""),
                "created_at": doc.get("created_at", ""),
                "updated_at": doc.get("updated_at", ""),
                "time": _relative_time(doc.get("created_at", "")),
                "changes": {
                    "added": additions,
                    "removed": deletions,
                    "files": files_changed
                },
                # AI Analysis Data
                "aiSummary": doc.get("ai_summary"),
                "aiIssues": doc.get("ai_issues", []),
                "healthScore": doc.get("health_score"),
                "analysisStatus": doc.get("analysis_status", "pending"),

                # Auto-Fix Data
                "isAutoFix": doc.get("is_auto_fix", False),
                "autoFixFor": doc.get("auto_fix_for"),
                "autoFixMrs": doc.get("auto_fix_mrs", []),
                "autoFixStatus": doc.get("auto_fix_status"),
            })

        return result

    except Exception as e:
        print(f"[ERROR] Failed to fetch MRs from MongoDB: {e}")
        # Return empty list on error
        return []


async def link_auto_fix_to_original_mr(
    repo_id: str,
    original_mr_iid: int,
    auto_fix_mr_iid: int,
    auto_fix_branch: str
) -> Dict:
    """
    Link an auto-fix MR to its original MR in MongoDB.

    When Gatekeeper generates an auto-fix MR:
    1. Mark the auto-fix MR with is_auto_fix=True and auto_fix_for=original_mr_iid
    2. Add the auto-fix MR's IID to the original MR's auto_fix_mrs list

    Args:
        repo_id: Repository ID
        original_mr_iid: Original MR's GitLab IID
        auto_fix_mr_iid: Auto-fix MR's GitLab IID
        auto_fix_branch: Auto-fix branch name

    Returns:
        Status dict with linked MR information
    """
    try:
        if not MONGO_CONNECTION_STRING:
            print("[⚠️] MongoDB not configured - auto-fix link stored in memory only")
            # Update in-memory cache
            for mr in _merge_requests.get(repo_id, []):
                if mr.get("gitlab_mr_id") == auto_fix_mr_iid:
                    mr["is_auto_fix"] = True
                    mr["auto_fix_for"] = original_mr_iid
                    mr["auto_fix_status"] = "applied"
                if mr.get("gitlab_mr_id") == original_mr_iid:
                    if "auto_fix_mrs" not in mr:
                        mr["auto_fix_mrs"] = []
                    if auto_fix_mr_iid not in mr["auto_fix_mrs"]:
                        mr["auto_fix_mrs"].append(auto_fix_mr_iid)
            return {
                "status": "linked_memory",
                "original_mr": original_mr_iid,
                "auto_fix_mr": auto_fix_mr_iid
            }

        # Update auto-fix MR document
        auto_fix_result = await mongo_client.update_one(
            collection_name=MRS_COLLECTION,
            filter={
                "repository_id": repo_id,
                "gitlab_mr_id": auto_fix_mr_iid
            },
            update={
                "$set": {
                    "is_auto_fix": True,
                    "auto_fix_for": original_mr_iid,
                    "auto_fix_status": "applied",
                    "source_branch": auto_fix_branch
                }
            }
        )

        # Update original MR document
        original_result = await mongo_client.update_one(
            collection_name=MRS_COLLECTION,
            filter={
                "repository_id": repo_id,
                "gitlab_mr_id": original_mr_iid
            },
            update={
                "$push": {"auto_fix_mrs": auto_fix_mr_iid}
            }
        )

        print(f"[✅] Linked auto-fix MR {auto_fix_mr_iid} to original MR {original_mr_iid}")

        return {
            "status": "linked",
            "original_mr": original_mr_iid,
            "auto_fix_mr": auto_fix_mr_iid,
            "auto_fix_modified": auto_fix_result > 0,
            "original_modified": original_result > 0
        }

    except Exception as e:
        print(f"[ERROR] Failed to link auto-fix MR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


async def submit_mr_feedback(
    repo_id: str,
    mr_id: str,
    vote: str,
    comment: str,
    user_id: str
) -> Dict:
    """
    Store feedback on AI analysis for a merge request.

    Feedback is stored in a separate collection for analytics.

    Args:
        repo_id: Repository ID
        mr_id: Merge Request ID
        vote: User vote ("helpful" or "unhelpful")
        comment: Optional comment text
        user_id: User ID submitting feedback

    Returns:
        Success response

    Raises:
        HTTPException: If storage fails
    """
    try:
        feedback_doc = {
            "repo_id": repo_id,
            "mr_id": mr_id,
            "vote": vote,
            "comment": comment,
            "user_id": user_id,
            "created_at": datetime.now().isoformat()
        }

        if MONGO_CONNECTION_STRING:
            doc_id = await mongo_client.insert_one(
                collection_name="ai_feedback",
                document=feedback_doc
            )
            print(f"[✅] Stored feedback for MR {mr_id} with ID: {doc_id}")
        else:
            print("[⚠️] MongoDB not configured - feedback not stored")

        return {
            "status": "recorded",
            "message": "Feedback recorded successfully"
        }

    except Exception as e:
        print(f"[ERROR] Failed to submit feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


async def update_mr_analysis(
    repo_id: str,
    mr_iid: int,
    analysis_data: Dict
) -> bool:
    """
    Update an MR with AI analysis results.

    Args:
        repo_id: Repository ID
        mr_iid: Merge Request IID
        analysis_data: Dictionary containing ai_summary, ai_issues, health_score, etc.

    Returns:
        True if update successful, False otherwise
    """
    try:
        print(f"[DEBUG] Updating MR analysis: repo_id={repo_id} (type: {type(repo_id).__name__}), mr_iid={mr_iid} (type: {type(mr_iid).__name__})")
        print(f"[DEBUG] Analysis data keys: {list(analysis_data.keys())}")
        print(f"[DEBUG] Analysis status: {analysis_data.get('analysis_status', 'NOT_SET')}")

        if MONGO_CONNECTION_STRING:
            result = await mongo_client.update_one(
                collection_name=MRS_COLLECTION,
                filter={
                    "repository_id": repo_id,
                    "gitlab_mr_id": mr_iid
                },
                update={"$set": analysis_data}
            )

            if result:
                print(f"[✅] Updated MR {mr_iid} analysis in MongoDB")
                return True
            else:
                print(f"[⚠️] No MR found to update: repo_id={repo_id}, mr_iid={mr_iid}")
                # Try to find the MR to debug
                existing = await mongo_client.find_one(
                    collection_name=MRS_COLLECTION,
                    filter={"repository_id": repo_id}
                )
                if existing:
                    print(f"[DEBUG] Found MR with different ID structure:")
                    print(f"[DEBUG] Existing repo_id: {existing.get('repository_id')} (type: {type(existing.get('repository_id')).__name__})")
                    print(f"[DEBUG] Existing gitlab_mr_id: {existing.get('gitlab_mr_id')} (type: {type(existing.get('gitlab_mr_id')).__name__})")
                return False
        else:
            # Update in-memory cache
            for mr in _merge_requests.get(repo_id, []):
                if mr.get("gitlab_mr_id") == mr_iid:
                    mr.update(analysis_data)
                    print(f"[✅] Updated MR {mr_iid} analysis in memory")
                    return True
            return False

    except Exception as e:
        print(f"[ERROR] Failed to update MR analysis: {e}")
        return False


async def add_mr_progress_log(
    repo_id: str,
    mr_iid: int,
    step: str,
    message: str,
    status: str = "running"
) -> bool:
    """
    Add a progress log entry to an MR.

    Args:
        repo_id: Repository ID
        mr_iid: Merge Request IID
        step: Step identifier (e.g., "fetching", "analyzing")
        message: User-friendly message describing the current action
        status: Status of the step (running, completed, failed)

    Returns:
        True if update successful, False otherwise
    """
    try:
        from datetime import datetime, timezone

        log_entry = {
            "step": step,
            "message": message,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if MONGO_CONNECTION_STRING:
            result = await mongo_client.update_one(
                collection_name=MRS_COLLECTION,
                filter={
                    "repository_id": repo_id,
                    "gitlab_mr_id": mr_iid
                },
                update={
                    "$push": {"progress_logs": log_entry}
                }
            )
            return result > 0
        else:
            # Update in-memory cache
            for mr in _merge_requests.get(repo_id, []):
                if mr.get("gitlab_mr_id") == mr_iid:
                    if "progress_logs" not in mr:
                        mr["progress_logs"] = []
                    mr["progress_logs"].append(log_entry)
                    return True
            return False
    except Exception as e:
        print(f"[ERROR] Failed to add progress log: {e}")
        return False


async def get_mr_progress_logs(repo_id: str, mr_iid: int) -> List[Dict]:
    """
    Get progress logs for a merge request.

    Args:
        repo_id: Repository ID
        mr_iid: Merge Request IID

    Returns:
        List of progress log entries
    """
    try:
        if MONGO_CONNECTION_STRING:
            mr_doc = await mongo_client.find_one(
                collection_name=MRS_COLLECTION,
                filter={
                    "repository_id": repo_id,
                    "gitlab_mr_id": mr_iid
                }
            )
            if mr_doc:
                return mr_doc.get("progress_logs", [])
        else:
            # Get from in-memory cache
            for mr in _merge_requests.get(repo_id, []):
                if mr.get("gitlab_mr_id") == mr_iid:
                    return mr.get("progress_logs", [])
        return []
    except Exception as e:
        print(f"[ERROR] Failed to get progress logs: {e}")
        return []


def is_config_file(filepath: str) -> bool:
    filename = os.path.basename(filepath).lower()
    if filename.startswith(".env"):
        return True
    if filename in ["config.js", "config.py", "settings.py", "database.js", "database.py", "docker-compose.yml", "docker-compose.yaml"]:
        return True
    return False


async def _get_file_content_from_gitlab(gitlab_session, project_id: str, file_path: str) -> str:
    try:
        file_result = await gitlab_session.call_tool(
            name="get_file_contents",
            arguments={
                "project_id": str(project_id),
                "file_path": file_path,
            }
        )
        if hasattr(file_result, 'content') and file_result.content:
            file_data = json.loads(file_result.content[0].text)
            content = file_data.get("content", "")
            if file_data.get("encoding") == "base64":
                import base64
                padding_needed = (4 - len(content) % 4) % 4
                if padding_needed:
                    content += '=' * padding_needed
                content = content.replace('-', '+').replace('_', '/')
                return base64.b64decode(content).decode('utf-8', errors='replace')
            return content
    except Exception as e:
        print(f"[⚠️] Failed to fetch file content for {file_path}: {e}")
    return ""


import re

# Regex patterns for matching credentials
mongo_uri_pattern = re.compile(r'mongodb(?:\+srv)?://[^\s"\'`]+')
fivetran_key_pattern = re.compile(r'(?:fivetran_api_key|fivetran_key|fivetran_api_user|fivetran_user)\s*[=:]\s*["\'`]?([a-zA-Z0-9_-]+)["\'`]?', re.IGNORECASE)
fivetran_secret_pattern = re.compile(r'(?:fivetran_api_secret|fivetran_secret|fivetran_api_password|fivetran_password)\s*[=:]\s*["\'`]?([a-zA-Z0-9_-]+)["\'`]?', re.IGNORECASE)


async def scan_repository(user_id: str, repo_id: str) -> Dict:
    """
    Scans the repository's files (e.g. .env, config.js, settings.py) for credentials.
    """
    # 1. Get gitlab_session
    gitlab_session = mcp_service.gitlab_session
    if not gitlab_session:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitLab MCP service is currently unavailable"
        )

    # 2. Get repository tree
    files_to_scan = []
    try:
        page_token = None
        while len(files_to_scan) < 50: # Limit to first 50 files/config files to avoid huge searches
            arguments = {
                "project_id": str(repo_id),
                "recursive": True,
            }
            if page_token:
                arguments["page_token"] = page_token
                arguments["pagination"] = "keyset"

            tree_result = await gitlab_session.call_tool(
                name="get_repository_tree",
                arguments=arguments
            )

            if not (hasattr(tree_result, 'content') and tree_result.content):
                break

            tree_data = json.loads(tree_result.content[0].text)
            items = tree_data.get("items", []) if isinstance(tree_data, dict) else tree_data

            next_token = None
            if isinstance(tree_data, dict):
                next_token = tree_data.get("next_page_token")

            if isinstance(items, list):
                for item in items:
                    if item.get("type") == "blob":
                        path = item.get("path", "")
                        if is_config_file(path):
                            files_to_scan.append(path)

            if next_token:
                page_token = next_token
            else:
                break
    except Exception as e:
        print(f"[ERROR] Failed to fetch repository tree: {e}")
        # If we failed to get tree, return empty results gracefully
        return {
            "mongodb_uri": None,
            "fivetran_api_key": None,
            "fivetran_api_secret": None,
            "detected_in_files": []
        }

    # Limit scanning to at most 10 config files
    files_to_scan = files_to_scan[:10]

    detected_mongodb_uri = None
    detected_fivetran_key = None
    detected_fivetran_secret = None
    detected_files = []

    for file_path in files_to_scan:
        content = await _get_file_content_from_gitlab(gitlab_session, repo_id, file_path)
        if not content:
            continue

        file_matched = False

        # 1. Match MongoDB URI
        mongo_match = mongo_uri_pattern.search(content)
        if mongo_match and not detected_mongodb_uri:
            detected_mongodb_uri = mongo_match.group(0)
            file_matched = True

        # 2. Match Fivetran key
        key_match = fivetran_key_pattern.search(content)
        if key_match and not detected_fivetran_key:
            detected_fivetran_key = key_match.group(1)
            file_matched = True

        # 3. Match Fivetran secret
        secret_match = fivetran_secret_pattern.search(content)
        if secret_match and not detected_fivetran_secret:
            detected_fivetran_secret = secret_match.group(1)
            file_matched = True

        if file_matched:
            detected_files.append(file_path)

    return {
        "mongodb_uri": detected_mongodb_uri,
        "fivetran_api_key": detected_fivetran_key,
        "fivetran_api_secret": detected_fivetran_secret,
        "detected_in_files": detected_files
    }


async def onboard_repository(user_id: str, repo_id: str, data: Dict) -> Dict:
    """
    Onboards a repository by saving its configurations, optionally encrypting sensitive credentials.
    """
    # 1. Retrieve inputs
    mongodb_uri = data.get("mongodb_uri")
    fivetran_api_key = data.get("fivetran_api_key")
    fivetran_api_secret = data.get("fivetran_api_secret")
    encrypt_credentials = data.get("encrypt_credentials", True)

    # 2. Perform encryption if requested
    if encrypt_credentials:
        from services.encryption_service import encrypt_value
        if mongodb_uri:
            mongodb_uri = encrypt_value(mongodb_uri)
        if fivetran_api_key:
            fivetran_api_key = encrypt_value(fivetran_api_key)
        if fivetran_api_secret:
            fivetran_api_secret = encrypt_value(fivetran_api_secret)

    # 3. Get user's GitLab token
    gitlab_token = None
    user_session = auth_service.get_user_session(user_id)
    if user_session:
        gitlab_token = user_session.get("gitlab_access_token")
    if not gitlab_token:
        gitlab_token = GITLAB_PERSONAL_ACCESS_TOKEN

    # 4. Fetch details from GitLab
    headers = {"Authorization": f"Bearer {gitlab_token}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITLAB_BASE_URL}/api/v4/projects/{repo_id}",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            project = response.json()
    except Exception as e:
        # Fallback project details if GitLab fetch fails
        project = {
            "id": repo_id,
            "name": f"Project {repo_id}",
            "path_with_namespace": f"imported/project_{repo_id}",
            "visibility": "private",
            "web_url": f"https://gitlab.com/imported/project_{repo_id}",
            "description": "Onboarded project"
        }

    # 5. Create or update repository document
    new_repo = {
        "id": str(project.get("id", repo_id)),
        "name": project.get("name", f"Project {repo_id}"),
        "full_name": project.get("path_with_namespace", f"imported/project_{repo_id}"),
        "visibility": _map_gitlab_visibility(project.get("visibility", "private")),
        "url": project.get("web_url", ""),
        "last_sync": datetime.now().isoformat() if MONGO_CONNECTION_STRING else datetime.now(),
        "health_score": 100.0,
        "status": RepositoryStatus.ACTIVE,
        "description": project.get("description", ""),
        "created_at": datetime.fromisoformat(project.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")) if "created_at" in project else datetime.now(),
        "avatar_url": project.get("avatar_url"),
        "executive_summary": "Repository onboarded successfully.",
        "vector_analysis": {
            "security": "100.0%",
            "performance": "100.0%",
            "complexity": "100.0%"
        },
        # Credential fields
        "mongodb_uri": mongodb_uri,
        "fivetran_api_key": fivetran_api_key,
        "fivetran_api_secret": fivetran_api_secret,
        "credentials_encrypted": encrypt_credentials,
        "onboarded": True,
        "avg_review_time": 2.5,
        "mrs_reviewed": 0
    }

    # Check if document already exists
    existing = await _find_repository(user_id, str(repo_id))
    if existing:
        # Update existing repository record in MongoDB
        if MONGO_CONNECTION_STRING:
            # Add user_id and connection timestamp
            new_repo["user_id"] = user_id
            new_repo["connected_at"] = existing.get("connected_at", datetime.now().isoformat())

            # Use direct update_one on mongo_client
            # We serialize date objects if any
            if isinstance(new_repo["created_at"], datetime):
                new_repo["created_at"] = new_repo["created_at"].isoformat()
            if isinstance(new_repo["last_sync"], datetime):
                new_repo["last_sync"] = new_repo["last_sync"].isoformat()

            await mongo_client.update_one(
                collection_name=REPOS_COLLECTION,
                filter={"user_id": user_id, "id": str(repo_id)},
                update={"$set": new_repo}
            )
            print(f"[✅] Onboarded/Updated repository {new_repo['name']} in MongoDB")
    else:
        # Save new repository in memory and db
        _repositories[new_repo["id"]] = new_repo
        _merge_requests[new_repo["id"]] = []
        _policies[new_repo["id"]] = []
        await _store_repository(user_id, new_repo)

    return {
        "id": new_repo["id"],
        "name": new_repo["name"],
        "full_name": new_repo["full_name"],
        "url": new_repo["url"],
        "status": _get_enum_value(new_repo["status"]),
        "onboarded": True,
        "message": "Repository onboarded and credentials saved successfully"
    }


async def update_repository_credentials(repo_id: str, data: Dict) -> Dict:
    """
    Update repository credentials.

    Args:
        repo_id: Repository ID
        data: Dictionary containing credentials to update

    Returns:
        Updated repository information
    """
    # 1. Retrieve inputs
    mongodb_uri = data.get("mongodb_uri")
    fivetran_api_key = data.get("fivetran_api_key")
    fivetran_api_secret = data.get("fivetran_api_secret")
    encrypt_credentials = data.get("encrypt_credentials", True)

    # 2. Verify repository exists in MongoDB
    if not MONGO_CONNECTION_STRING:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB connection not available"
        )

    existing_repo = await mongo_client.find_one(
        collection_name=REPOS_COLLECTION,
        filter={"id": repo_id}
    )

    if not existing_repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repo_id} not found. Please onboard the repository first."
        )

    # 3. Perform encryption if requested
    if encrypt_credentials:
        from services.encryption_service import encrypt_value
        if mongodb_uri:
            mongodb_uri = encrypt_value(mongodb_uri)
        if fivetran_api_key:
            fivetran_api_key = encrypt_value(fivetran_api_key)
        if fivetran_api_secret:
            fivetran_api_secret = encrypt_value(fivetran_api_secret)

    # 4. Prepare update data - only include provided fields
    update_data = {}
    if mongodb_uri is not None:
        update_data["mongodb_uri"] = mongodb_uri
    if fivetran_api_key is not None:
        update_data["fivetran_api_key"] = fivetran_api_key
    if fivetran_api_secret is not None:
        update_data["fivetran_api_secret"] = fivetran_api_secret

    # Always set encryption flag
    update_data["credentials_encrypted"] = encrypt_credentials

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No credentials provided for update"
        )

    # 5. Update repository in MongoDB
    await mongo_client.update_one(
        collection_name=REPOS_COLLECTION,
        filter={"id": repo_id},
        update={"$set": update_data}
    )

    print(f"[✅] Updated credentials for repository {repo_id}")

    # 6. Get updated repository
    updated_repo = await mongo_client.find_one(
        collection_name=REPOS_COLLECTION,
        filter={"id": repo_id}
    )

    return {
        "message": "Repository credentials updated successfully",
        "mongodb_uri_configured": bool(updated_repo.get("mongodb_uri")),
        "fivetran_key_configured": bool(updated_repo.get("fivetran_api_key")),
        "fivetran_secret_configured": bool(updated_repo.get("fivetran_api_secret")),
        "credentials_encrypted": updated_repo.get("credentials_encrypted", False)
    }

