import os
import unittest
from unittest.mock import patch

import server
from mcp.server.mcpserver.exceptions import ToolError


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self.data = data
        self.content = b"response" if data else b""

    def json(self):
        return self.data


class GitHubServerTests(unittest.TestCase):
    def setUp(self):
        self.token_patch = patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"})
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)

    @patch("server.requests.request")
    def test_repo_info_uses_token_and_returns_repository(self, request):
        repository = {"full_name": "octocat/hello-world"}
        request.return_value = FakeResponse(200, repository)

        result = server.github_repo_info("octocat", "hello-world")

        self.assertEqual(result, repository)
        authorization = request.call_args.kwargs["headers"].get("Authorization", "")
        self.assertTrue(authorization.endswith("test-token"))

    @patch("server.requests.request")
    def test_github_error_is_returned_with_diagnostic(self, request):
        request.return_value = FakeResponse(404, {"message": "Not Found"})

        with self.assertRaisesRegex(ToolError, "404.*Not Found"):
            server.github_repo_info("unknown", "missing")

    @patch("server.requests.request")
    def test_reading_a_directory_returns_actionable_tool_error(self, request):
        request.return_value = FakeResponse(200, [{"type": "file"}])

        with self.assertRaisesRegex(ToolError, "points to a directory"):
            server.github_read_file("octocat", "hello-world", "docs")

    @patch("server.requests.request")
    def test_file_update_does_not_treat_permission_error_as_missing(self, request):
        request.return_value = FakeResponse(401, {"message": "Bad credentials"})

        with self.assertRaisesRegex(ToolError, "401.*Bad credentials"):
            server.github_create_or_update_file(
                "octocat", "hello-world", "README.md", "text", branch="main"
            )

        request.assert_called_once()

    @patch("server.requests.request")
    def test_file_create_follows_not_found_lookup(self, request):
        request.side_effect = [
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(201, {"content": {"path": "README.md"}}),
        ]

        result = server.github_create_or_update_file(
            "octocat", "hello-world", "README.md", "text", branch="main"
        )

        self.assertEqual(result, {"content": {"path": "README.md"}})
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("sha", request.call_args_list[1].kwargs["json"])

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_token_has_actionable_diagnostic(self):
        with self.assertRaisesRegex(ToolError, "Missing GITHUB_TOKEN"):
            server.github_headers()


if __name__ == "__main__":
    unittest.main()
