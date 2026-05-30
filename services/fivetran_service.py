import base64
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from services import mcp_service, mongo_client
from services.encryption_service import decrypt_value

REPOS_COLLECTION = "connected_repositories"
FIVETRAN_EVENTS_COLLECTION = "fivetran_pipeline_events"
DEFAULT_FIVETRAN_BASE_URL = "https://api.fivetran.com/v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _resolve_fivetran_credentials(project_id: str, target_branch: Optional[str] = None) -> Dict[str, Any]:
    repo = await mongo_client.find_one(REPOS_COLLECTION, {"id": str(project_id)})
    if not repo:
        return {"status": "missing_credentials", "reason": "repository_not_found"}

    key = repo.get("fivetran_api_key")
    secret = repo.get("fivetran_api_secret")

    branch_credentials = repo.get("branch_credentials", {}) or {}
    if target_branch and target_branch in branch_credentials:
        branch_creds = branch_credentials[target_branch] or {}
        if branch_creds.get("fivetran_api_key"):
            key = branch_creds.get("fivetran_api_key")
        if branch_creds.get("fivetran_api_secret"):
            secret = branch_creds.get("fivetran_api_secret")

    if repo.get("credentials_encrypted", False):
        key = decrypt_value(key) if key else key
        secret = decrypt_value(secret) if secret else secret

    if not key or not secret:
        return {"status": "missing_credentials", "reason": "fivetran_key_or_secret_missing"}

    return {"status": "ok", "api_key": key, "api_secret": secret}


def _build_auth_header(api_key: str, api_secret: str) -> str:
    token_raw = f"{api_key}:{api_secret}".encode("utf-8")
    token = base64.b64encode(token_raw).decode("utf-8")
    return f"Basic {token}"


def _rest_call(method: str, path: str, auth_header: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base_url = os.getenv("FIVETRAN_BASE_URL", DEFAULT_FIVETRAN_BASE_URL).rstrip("/")
    url = f"{base_url}{path}"
    response = requests.request(
        method=method,
        url=url,
        headers={
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


async def _list_connections(auth_header: str) -> Dict[str, Any]:
    if mcp_service.fivetran_session:
        # Expected MCP contract can vary by server implementation, so REST remains default.
        pass
    return _rest_call("GET", "/connections", auth_header)


async def _get_connection_schema(connection_id: str, auth_header: str) -> Dict[str, Any]:
    if mcp_service.fivetran_session:
        # Expected MCP contract can vary by server implementation, so REST remains default.
        pass
    return _rest_call("GET", f"/connections/{connection_id}/schemas", auth_header)


def _extract_delta_changes(schema_delta: Any) -> List[Dict[str, Any]]:
    if not schema_delta or not getattr(schema_delta, "changes", None):
        return []

    normalized = []
    for change in schema_delta.changes:
        normalized.append(
            {
                "collection": getattr(change, "collection", None),
                "change_type": getattr(change, "change_type", None),
                "field_name": getattr(change, "field_name", None),
                "old_value": getattr(change, "old_value", None),
                "new_value": getattr(change, "new_value", None),
            }
        )
    return normalized


def _schema_contains_collection(schema_payload: Dict[str, Any], collection_name: str) -> bool:
    if not schema_payload:
        return False

    data = schema_payload.get("data", {})
    if not isinstance(data, dict):
        return False

    schema_config = data.get("schemas", {})
    if not isinstance(schema_config, dict):
        return False

    target = collection_name.lower()
    for schema_name, schema_body in schema_config.items():
        if schema_name.lower() == target:
            return True
        if not isinstance(schema_body, dict):
            continue
        tables = schema_body.get("tables", {})
        if isinstance(tables, dict):
            for table_name in tables:
                if str(table_name).lower() == target:
                    return True
    return False


def _plan_actions(connection_id: str, impacted_collections: List[str], dry_run: bool) -> List[Dict[str, Any]]:
    return [
        {
            "action": "reload_schema",
            "connection_id": connection_id,
            "payload": {"connection_id": connection_id},
            "dry_run": dry_run,
            "reason": f"schema delta touches collections: {', '.join(sorted(set(impacted_collections)))}",
        },
        {
            "action": "trigger_sync",
            "connection_id": connection_id,
            "payload": {"connection_id": connection_id},
            "dry_run": dry_run,
            "reason": "run connector sync after schema refresh",
        },
    ]


async def analyze_schema_impact(
    project_id: str,
    mr_iid: int,
    schema_delta: Any,
    target_branch: Optional[str] = None,
) -> Dict[str, Any]:
    execution_mode = os.getenv("FIVETRAN_EXECUTION_MODE", "dry_run").strip().lower() or "dry_run"
    dry_run = execution_mode != "execute"

    credential_result = await _resolve_fivetran_credentials(str(project_id), target_branch)
    if credential_result.get("status") != "ok":
        report = {
            "status": "missing_credentials",
            "execution_mode": execution_mode,
            "impacted_connectors": [],
            "proposed_actions": [],
            "error": credential_result.get("reason"),
            "analyzed_at": _utc_now_iso(),
        }
        await log_fivetran_event(str(project_id), mr_iid, target_branch, report)
        return report

    auth_header = _build_auth_header(credential_result["api_key"], credential_result["api_secret"])
    normalized_changes = _extract_delta_changes(schema_delta)
    impacted_collections = sorted({c.get("collection") for c in normalized_changes if c.get("collection")})

    try:
        connection_data = await _list_connections(auth_header)
        raw_connections = connection_data.get("data", {}).get("items", [])

        impacted_connectors = []
        proposed_actions: List[Dict[str, Any]] = []

        for conn in raw_connections:
            connection_id = conn.get("id")
            if not connection_id:
                continue

            schema_payload = await _get_connection_schema(connection_id, auth_header)
            touched = any(_schema_contains_collection(schema_payload, name) for name in impacted_collections)
            if not touched:
                continue

            impacted_connectors.append(
                {
                    "connection_id": connection_id,
                    "service": conn.get("service"),
                    "group_id": conn.get("group_id"),
                    "status": conn.get("status"),
                    "impacted_collections": impacted_collections,
                }
            )
            proposed_actions.extend(_plan_actions(connection_id, impacted_collections, dry_run))

        status = "ok" if impacted_connectors else "no_impacted_connectors"
        report = {
            "status": status,
            "execution_mode": execution_mode,
            "impacted_connectors": impacted_connectors,
            "proposed_actions": proposed_actions,
            "schema_delta": normalized_changes,
            "analyzed_at": _utc_now_iso(),
        }
        await log_fivetran_event(str(project_id), mr_iid, target_branch, report)
        return report
    except requests.HTTPError as exc:
        report = {
            "status": "api_error",
            "execution_mode": execution_mode,
            "impacted_connectors": [],
            "proposed_actions": [],
            "error": f"http_error: {exc}",
            "analyzed_at": _utc_now_iso(),
        }
        await log_fivetran_event(str(project_id), mr_iid, target_branch, report)
        return report
    except Exception as exc:
        report = {
            "status": "api_error",
            "execution_mode": execution_mode,
            "impacted_connectors": [],
            "proposed_actions": [],
            "error": str(exc),
            "analyzed_at": _utc_now_iso(),
        }
        await log_fivetran_event(str(project_id), mr_iid, target_branch, report)
        return report


def format_impact_report_markdown(report: Dict[str, Any]) -> str:
    lines = ["## Fivetran Impact & Recovery Plan"]
    lines.append(f"- Status: `{report.get('status', 'unknown')}`")
    lines.append(f"- Execution mode: `{report.get('execution_mode', 'dry_run')}`")

    error = report.get("error")
    if error:
        lines.append(f"- Error: `{error}`")

    connectors = report.get("impacted_connectors", []) or []
    if connectors:
        lines.append("")
        lines.append("### Impacted connectors")
        for connector in connectors:
            lines.append(
                f"- `{connector.get('connection_id')}` ({connector.get('service', 'unknown')}) "
                f"collections: {', '.join(connector.get('impacted_collections', []))}"
            )
    else:
        lines.append("- Impacted connectors: none")

    actions = report.get("proposed_actions", []) or []
    if actions:
        lines.append("")
        lines.append("### Proposed actions")
        for action in actions:
            lines.append(
                f"- `{action.get('action')}` on `{action.get('connection_id')}` "
                f"(dry_run={action.get('dry_run', True)})"
            )

    return "\n".join(lines)


async def execute_actions(
    project_id: str,
    mr_iid: int,
    actions: List[Dict[str, Any]],
    target_branch: Optional[str] = None,
) -> Dict[str, Any]:
    credential_result = await _resolve_fivetran_credentials(str(project_id), target_branch)
    if credential_result.get("status") != "ok":
        return {
            "status": "missing_credentials",
            "executed_actions": [],
            "failed_actions": actions,
            "error": credential_result.get("reason"),
            "executed_at": _utc_now_iso(),
        }

    auth_header = _build_auth_header(credential_result["api_key"], credential_result["api_secret"])

    executed_actions = []
    failed_actions = []
    for action in actions:
        action_name = action.get("action")
        connection_id = action.get("connection_id")
        if not action_name or not connection_id:
            failed_actions.append({"action": action, "error": "invalid_action_payload"})
            continue

        try:
            if action_name == "reload_schema":
                response = _rest_call("POST", f"/connections/{connection_id}/schemas/reload", auth_header, {})
            elif action_name == "trigger_sync":
                response = _rest_call("POST", f"/connections/{connection_id}/force", auth_header, {})
            else:
                failed_actions.append({"action": action, "error": f"unsupported_action:{action_name}"})
                continue

            executed_actions.append(
                {
                    "action": action_name,
                    "connection_id": connection_id,
                    "response": response,
                }
            )
        except Exception as exc:
            failed_actions.append(
                {
                    "action": action,
                    "connection_id": connection_id,
                    "error": str(exc),
                }
            )

    status = "ok" if not failed_actions else "partial_failure"
    report = {
        "status": status,
        "executed_actions": executed_actions,
        "failed_actions": failed_actions,
        "executed_at": _utc_now_iso(),
    }
    await log_fivetran_event(str(project_id), mr_iid, target_branch, {"execution_result": report})
    return report


async def log_fivetran_event(project_id: str, mr_iid: int, target_branch: Optional[str], payload: Dict[str, Any]) -> None:
    try:
        await mongo_client.insert_one(
            FIVETRAN_EVENTS_COLLECTION,
            {
                "project_id": str(project_id),
                "mr_iid": int(mr_iid),
                "target_branch": target_branch,
                "event": payload,
                "timestamp": _utc_now_iso(),
            },
        )
    except Exception as exc:
        print(f"[WARN] Failed to persist Fivetran event: {exc}")
