import base64
import os
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    raise RuntimeError(
        "Missing GITHUB_TOKEN environment variable. "
        "Set it to a GitHub personal access token before starting the server."
    )

# Create the MCP server and mount it on FastAPI.
mcp = FastMCP("github")
app = FastAPI()
app.mount("/mcp", mcp.sse_app())


def github_headers() -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-mcp-claude",
    }


def github_request(method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None) -> Any:
    resp = requests.request(
        method,
        f"{GITHUB_API}{path}",
        headers=github_headers(),
        params=params,
        json=json,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GitHub API {method} {path} failed: {resp.status_code} {resp.text}"
        )
    if resp.content:
        return resp.json()
    return {}


def get_default_branch(owner: str, repo: str) -> str:
    data = github_request("GET", f"/repos/{owner}/{repo}")
    return data.get("default_branch", "main")


@mcp.tool()
def github_repo_info(owner: str, repo: str) -> Dict[str, Any]:
    """Get repository metadata for a public or private repo."""
    return github_request("GET", f"/repos/{owner}/{repo}")


@mcp.tool()
def github_list_contents(owner: str, repo: str, path: str = "", ref: Optional[str] = None) -> Any:
    """List contents of a repository path."""
    params = {}
    if ref:
        params["ref"] = ref
    endpoint = f"/repos/{owner}/{repo}/contents"
    if path:
        endpoint += f"/{path}"
    return github_request("GET", endpoint, params=params or None)


@mcp.tool()
def github_read_file(owner: str, repo: str, path: str, ref: Optional[str] = None) -> Dict[str, Any]:
    """Read and decode a file from a repository."""
    params = {"ref": ref} if ref else None
    data = github_request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)

    if isinstance(data, list):
        raise ValueError(f"'{path}' is a directory, not a file.")

    content_b64 = data.get("content", "")
    decoded = base64.b64decode(content_b64).decode("utf-8") if content_b64 else ""

    return {
        "path": path,
        "sha": data.get("sha"),
        "content": decoded,
        "encoding": data.get("encoding"),
        "size": data.get("size"),
        "download_url": data.get("download_url"),
    }


@mcp.tool()
def github_create_branch(owner: str, repo: str, branch_name: str, from_branch: Optional[str] = None) -> Dict[str, Any]:
    """Create a new branch from an existing branch."""
    base = from_branch or get_default_branch(owner, repo)
    ref_data = github_request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{base}")
    sha = ref_data["object"]["sha"]
    return github_request(
        "POST",
        f"/repos/{owner}/{repo}/git/refs",
        json={"ref": f"refs/heads/{branch_name}", "sha": sha},
    )


@mcp.tool()
def github_create_or_update_file(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str = "Update via Claude MCP server",
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a file in the repository."""
    target_branch = branch or get_default_branch(owner, repo)
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    existing_sha = None
    try:
        existing = github_request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": target_branch},
        )
        if isinstance(existing, dict):
            existing_sha = existing.get("sha")
    except Exception:
        existing_sha = None

    payload: Dict[str, Any] = {
        "message": message,
        "content": encoded,
        "branch": target_branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    return github_request("PUT", f"/repos/{owner}/{repo}/contents/{path}", json=payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
