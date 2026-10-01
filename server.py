import base64
import os
from typing import Any, Dict, List, Optional

import requests
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

GITHUB_API = "https://api.github.com"

mcp = MCPServer("github")


class GitHubAPIError(ToolError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


def get_github_token() -> str:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ToolError(
            "Missing GITHUB_TOKEN environment variable. "
            "Generate a GitHub PAT with repo access and set it before running the server."
        )
    return token


def github_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "claude-github-mcp-server",
    }
    header_name = "Authorization"
    auth_scheme = "Bearer"
    token = get_github_token()
    headers[header_name] = " ".join((auth_scheme, token))
    return headers


def github_request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    try:
        response = requests.request(
            method,
            f"{GITHUB_API}{path}",
            headers=github_headers(),
            params=params,
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise ToolError(
            f"GitHub API {method} {path} request failed "
            f"({type(exc).__name__}); check network connectivity and token configuration."
        ) from None

    if response.status_code >= 400:
        try:
            data = response.json()
        except ValueError:
            data = {}
        message = data.get("message") if isinstance(data, dict) else None
        errors = data.get("errors") if isinstance(data, dict) else None
        details = f": {message}" if message else ""
        if errors:
            details += f" ({errors})"
        raise GitHubAPIError(
            response.status_code,
            f"GitHub API {method} {path} failed "
            f"({response.status_code}){details}",
        )

    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        raise ToolError(
            f"GitHub API {method} {path} returned an invalid JSON response."
        ) from None


def github_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    return github_request("GET", path, params=params)


def github_post(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    return github_request("POST", path, payload=payload)


def github_put(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    return github_request("PUT", path, payload=payload)


def github_default_branch(owner: str, repo: str) -> str:
    repo_info = github_get(f"/repos/{owner}/{repo}")
    return repo_info.get("default_branch", "main")


@mcp.tool()
def github_repo_info(owner: str, repo: str) -> Dict[str, Any]:
    """Get repository metadata for a public or private repo available to the token."""
    return github_get(f"/repos/{owner}/{repo}")


@mcp.tool()
def github_list_contents(owner: str, repo: str, path: str = "") -> List[Dict[str, Any]]:
    """List repo contents; pass path='' for the root."""
    if path:
        return github_get(f"/repos/{owner}/{repo}/contents/{path}")
    return github_get(f"/repos/{owner}/{repo}/contents")


@mcp.tool()
def github_read_file(
    owner: str, repo: str, path: str, ref: Optional[str] = None
) -> Dict[str, Any]:
    """Read a file from a public or private repo. Returns the decoded file content."""
    params = {"ref": ref} if ref else None
    data = github_get(f"/repos/{owner}/{repo}/contents/{path}", params=params)

    if isinstance(data, list):
        raise ToolError(f"Path '{path}' points to a directory, not a file.")

    if data.get("type") != "file":
        raise ToolError(f"Path '{path}' is not a file.")

    content_b64 = data.get("content", "")
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8") if content_b64 else ""
    except (ValueError, UnicodeDecodeError):
        raise ToolError(f"File '{path}' is not valid UTF-8 text.") from None

    return {
        "path": path,
        "sha": data.get("sha"),
        "download_url": data.get("download_url"),
        "content": decoded,
        "encoding": data.get("encoding"),
        "size": data.get("size"),
    }


@mcp.tool()
def github_create_branch(
    owner: str,
    repo: str,
    branch_name: str,
    from_branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new git branch in a repo accessible to the token."""
    base_branch = from_branch or github_default_branch(owner, repo)
    ref = github_get(f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
    sha = ref["object"]["sha"]
    payload = {"ref": f"refs/heads/{branch_name}", "sha": sha}
    return github_post(f"/repos/{owner}/{repo}/git/refs", payload)


@mcp.tool()
def github_create_or_update_file(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str = "Update via Claude MCP server",
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a file in a repo. Works on public and private repos the token can access."""
    target_branch = branch or github_default_branch(owner, repo)
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    try:
        existing = github_get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": target_branch},
        )
    except GitHubAPIError as exc:
        if exc.status_code != 404:
            raise
        existing = None

    payload: Dict[str, Any] = {
        "message": message,
        "content": encoded_content,
        "branch": target_branch,
    }

    if isinstance(existing, dict) and existing.get("sha"):
        payload["sha"] = existing["sha"]

    return github_put(f"/repos/{owner}/{repo}/contents/{path}", payload)


@mcp.tool()
def github_create_issue(
    owner: str, repo: str, title: str, body: str = ""
) -> Dict[str, Any]:
    """Create an issue in a repo if the token has permission."""
    payload = {"title": title, "body": body}
    return github_post(f"/repos/{owner}/{repo}/issues", payload)


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
