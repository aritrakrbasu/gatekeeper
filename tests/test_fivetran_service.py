import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services import fivetran_service


class TestFivetranService(unittest.IsolatedAsyncioTestCase):
    async def test_credentials_branch_override_precedence(self):
        repo_doc = {
            "id": "123",
            "fivetran_api_key": "repo_key",
            "fivetran_api_secret": "repo_secret",
            "credentials_encrypted": False,
            "branch_credentials": {
                "main": {
                    "fivetran_api_key": "branch_key",
                    "fivetran_api_secret": "branch_secret",
                }
            },
        }
        with patch.object(fivetran_service.mongo_client, "find_one", AsyncMock(return_value=repo_doc)):
            result = await fivetran_service._resolve_fivetran_credentials("123", "main")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["api_key"], "branch_key")
            self.assertEqual(result["api_secret"], "branch_secret")

    async def test_missing_credentials_status(self):
        repo_doc = {
            "id": "123",
            "credentials_encrypted": False,
        }
        with patch.object(fivetran_service.mongo_client, "find_one", AsyncMock(return_value=repo_doc)):
            result = await fivetran_service._resolve_fivetran_credentials("123", None)
            self.assertEqual(result["status"], "missing_credentials")

    async def test_analyze_schema_impact_no_impacted_connectors(self):
        fake_delta = MagicMock()
        fake_delta.changes = [MagicMock(collection="users", change_type="added_field", field_name="name")]

        with patch.object(
            fivetran_service,
            "_resolve_fivetran_credentials",
            AsyncMock(return_value={"status": "ok", "api_key": "k", "api_secret": "s"}),
        ), patch.object(
            fivetran_service, "_list_connections",
            AsyncMock(return_value={"data": {"items": [{"id": "conn_1", "service": "snowflake"}]}})
        ), patch.object(
            fivetran_service, "_get_connection_schema",
            AsyncMock(return_value={"data": {"schemas": {"orders": {"tables": {"orders": {}}}}}})
        ), patch.object(
            fivetran_service, "log_fivetran_event", AsyncMock()
        ):
            report = await fivetran_service.analyze_schema_impact("123", 1, fake_delta, "main")
            self.assertEqual(report["status"], "no_impacted_connectors")
            self.assertEqual(report["proposed_actions"], [])

    async def test_execute_actions_unsupported_action(self):
        with patch.object(
            fivetran_service,
            "_resolve_fivetran_credentials",
            AsyncMock(return_value={"status": "ok", "api_key": "k", "api_secret": "s"}),
        ), patch.object(fivetran_service, "log_fivetran_event", AsyncMock()):
            report = await fivetran_service.execute_actions(
                "123",
                1,
                [{"action": "unknown", "connection_id": "conn_1"}],
                "main",
            )
            self.assertEqual(report["status"], "partial_failure")
            self.assertEqual(len(report["failed_actions"]), 1)


if __name__ == "__main__":
    unittest.main()
