import json
from unittest.mock import MagicMock, patch

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from mcp_manager.tools import factory as tool_factory
from mcp_manager.utils import mcp_tool


class McpToolTests(TestCase):
    @patch("mcp_manager.utils.subprocess.Popen")
    def test_mcp_tool_uses_generated_tool_cli_flags(self, mock_popen):
        process = MagicMock()
        process.communicate.return_value = ('{"ok": true}', "")
        mock_popen.return_value = process

        with patch("mcp_manager.utils.os.getenv", return_value="/tmp/github-mcp-server"):
            result = mcp_tool("get_file_contents", {"owner": "octo", "repo": "hello", "path": "/"})

        self.assertEqual(result, {"ok": True})
        cmd = mock_popen.call_args.args[0]
        self.assertIn("tools", cmd)
        self.assertIn("get_file_contents", cmd)
        self.assertIn("--owner", cmd)
        self.assertIn("octo", cmd)
        self.assertIn("--repo", cmd)
        self.assertIn("hello", cmd)
        self.assertIn("--path", cmd)
        self.assertIn("/", cmd)

    @patch("mcp_manager.utils.subprocess.Popen")
    def test_mcp_tool_defaults_to_repos_toolset(self, mock_popen):
        # The 'issues' toolset schema breaks mcpcurl's dynamic commands; default must stay minimal.
        process = MagicMock()
        process.communicate.return_value = ("[]", "")
        mock_popen.return_value = process

        with patch("mcp_manager.utils.os.getenv", return_value="/tmp/github-mcp-server"):
            mcp_tool("get_file_contents", {"owner": "octo", "repo": "hello"})

        server_cmd = mock_popen.call_args.args[0][2]
        self.assertIn("--toolsets repos stdio", server_cmd)

    @patch("mcp_manager.utils.subprocess.Popen")
    def test_mcp_tool_accepts_custom_toolsets(self, mock_popen):
        process = MagicMock()
        process.communicate.return_value = ("[]", "")
        mock_popen.return_value = process

        with patch("mcp_manager.utils.os.getenv", return_value="/tmp/github-mcp-server"):
            mcp_tool("list_pull_requests", {"owner": "octo", "repo": "hello"}, toolsets="pull_requests")

        server_cmd = mock_popen.call_args.args[0][2]
        self.assertIn("--toolsets pull_requests stdio", server_cmd)

    @patch("mcp_manager.utils.subprocess.Popen")
    def test_mcp_tool_read_only_adds_flag(self, mock_popen):
        process = MagicMock()
        process.communicate.return_value = ("[]", "")
        mock_popen.return_value = process

        with patch("mcp_manager.utils.os.getenv", return_value="/tmp/github-mcp-server"):
            mcp_tool("list_issues", {"owner": "octo", "repo": "hello"}, toolsets="issues", read_only=True)

        server_cmd = mock_popen.call_args.args[0][2]
        self.assertIn("--toolsets issues --read-only stdio", server_cmd)

    @patch("mcp_manager.tools.factory.mcp_tool")
    def test_get_branches_uses_repos_toolset(self, mock_mcp_tool):
        mock_mcp_tool.return_value = [{"name": "main"}]

        result = tool_factory.get_branches.run(owner="github", repo="github-mcp-server")

        self.assertEqual(result, [{"name": "main"}])
        mock_mcp_tool.assert_called_once_with(
            "list_branches",
            {"owner": "github", "repo": "github-mcp-server"},
            toolsets="repos",
            read_only=True,
        )

    @patch("mcp_manager.tools.factory.mcp_tool")
    def test_get_issue_uses_list_issues_schema(self, mock_mcp_tool):
        mock_mcp_tool.return_value = [{"number": 1, "title": "Example issue"}]

        result = tool_factory.get_issue.run(owner="octo", repo="hello")

        self.assertEqual(result, [{"number": 1, "title": "Example issue"}])
        mock_mcp_tool.assert_called_once_with(
            "list_issues",
            {"owner": "octo", "repo": "hello", "state": "OPEN", "perPage": 5},
            toolsets="issues",
            read_only=True,
        )


class RunCrewViewTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("run_crew")

    @patch("mcp_manager.views.run_crew_task.delay")
    def test_run_crew_rejects_post_without_csrf_token(self, mock_delay):
        response = self.client.post(
            self.url,
            data=json.dumps({"owner": "octo", "repo": "hello"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        mock_delay.assert_not_called()

    @patch("mcp_manager.views.run_crew_task.delay")
    @patch("mcp_manager.views.GeneratedDocument.objects.select_related")
    def test_run_crew_accepts_post_with_csrf_token(self, mock_select_related, mock_delay):
        mock_delay.return_value.id = "task-123"
        mock_select_related.return_value.order_by.return_value.first.return_value = None

        self.client.get(reverse("documentation_interface"))
        csrf_token = self.client.cookies["csrftoken"].value

        response = self.client.post(
            self.url,
            data=json.dumps({"owner": "octo", "repo": "hello"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 202)
        self.assertJSONEqual(
            response.content,
            {"task_id": "task-123", "status": "PENDING"},
        )
        mock_delay.assert_called_once_with(owner="octo", repo="hello")
