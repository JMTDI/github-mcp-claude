# server.py
import base64
import json
import os
from typing import Any, Dict, List, Optional

import requests
from mcp.server.fastmcp import FastMCP

GITHUB_API = "https://api.github.com"
TOKEN = os.getenv("GITHUB_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "Missing GITHUB_TOKEN environment variable. "
        "Set it to a GitHub PAT with access to the repos you need."
    )

mcp = FastMCP("github")


def github_headers() -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "claude-github-mcp-server",
    }


def github_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    resp = requests.get(
        f"{GITHUB_API}{path}",
        headers=github_headers(),
        params=params,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GitHub API GET {path} failed: {resp.status_code} {resp.text}"
        )
    return resp.json() if resp.content else {}


def github_put(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    resp = requests.put(
        f"{GITHUB_API}{path}",
        headers=github_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GitHub API PUT {path} failed: {resp.status_code} {resp.text}"
        )
    return resp.json() if resp.content else {}


def github_post(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    resp = requests.post(
        f"{GITHUB_API}{path}",
        headers=github_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GitHub API POST {path} failed: {resp.status_code} {resp.text}"
        )
    return resp.json() if resp.content else {}


def github_get_default_branch(owner: str, repo: str) -> str:
    info = github_get(f"/repos/{owner}/{repo}")
    return info.get("default_branch", "main")


@mcp.tool()
def github_repo_info(owner: str, repo: str) -> Dict[str, Any]:
    """Get GitHub repository metadata for a public or private repo accessible to the token."""
    return github_get(f"/repos/{owner}/{repo}")


@mcp.tool()
def github_list_contents(owner: str, repo: str, path: str = "") -> List[Dict[str, Any]]:
    """List files and folders in a repo path. Use path='' for repo root."""
    return github_get(f"/repos/{owner}/{repo}/contents/{path}") if path else github_get(
        f"/repos/{owner}/{repo}/contents"
    )


@mcp.tool()
def github_read_file(owner: str, repo: str, path: str, ref: Optional[str] = None) -> Dict[str, Any]:
    """Read a file from a public or private repo. Returns the decoded file contents and metadata."""
    params = {"ref": ref} if ref else None
    data = github_get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
    if isinstance(data, list):
        raise ValueError(f"Path '{path}' points to a directory, not a file.")
    if data.get("type") != "file":
        raise ValueError(f"Path '{path}' is not a file.")
    content_b64 = data.get("content", "")
    if not content_b64:
        return {
            "path": path,
            "sha": data.get("sha"),
            "download_url": data.get("download_url"),
            "content": "",
            "encoding": data.get("encoding"),
            "size": data.get("size"),
        }
    decoded = base64.b64decode(content_b64).decode("utf-8")
    return {
        "path": path,
        "sha": data.get("sha"),
        "download_url": data.get("download_url"),
        "content": decoded,
        "encoding": data.get("encoding"),
        "size": data.get("size"),
    }


@mcp.tool()
def github_create_branch(owner: str, repo: str, branch_name: str, from_branch: Optional[str] = None) -> Dict[str, Any]:
    """Create a new branch in the repo."""
    base = from_branch or github_get_default_branch(owner, repo)
    ref = github_get(f"/repos/{owner}/{repo}/git/ref/heads/{base}")
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
    """Create or update a file in a GitHub repo accessible to the token."""
    target_branch = branch or github_get_default_branch(owner, repo)
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    # Check existing file
    existing = None
    try:
        existing = github_get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": target_branch})
    except Exception:
        existing = None

    payload = {
        "message": message,
        "content": encoded,
        "branch": target_branch,
    }

    if isinstance(existing, dict) and existing.get("sha"):
        payload["sha"] = existing["sha"]

    return github_put(f"/repos/{owner}/{repo}/contents/{path}", payload)


@mcp.tool()
def github_create_issue(owner: str, repo: str, title: str, body: str = "") -> Dict[str, Any]:
    """Create an issue in a repo if the token has permission."""
    payload = {"title": title, "body": body}
    return github_post(f"/repos/{owner}/{repo}/issues", payload)


if __name__ == "__main__":
    # Run as SSE-based MCP server on port 8000
    # Claude config can point to http://localhost:8000/sse
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
