import json
from unittest.mock import MagicMock, patch

from django.test import TestCase

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
