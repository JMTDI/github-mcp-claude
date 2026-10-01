# GitHub MCP Server for Claude

This project exposes GitHub repository tools over MCP so Claude can:
- read public and private repos the token can access
- list repo contents
- read file contents
- create or update files
- create branches
- create issues

It runs as an MCP SSE server on port 8000.

## Requirements

- Python 3.10+
- A GitHub Personal Access Token (PAT)
- Repo access to the repos you want Claude to use

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set a GitHub token with access to the repositories Claude should use, then start
the server:

```bash
export GITHUB_TOKEN=github_pat_...
python server.py
```

The server listens on `http://0.0.0.0:8000` and exposes the SSE endpoint at
`http://localhost:8000/sse`. Add it to Claude Code with:

```bash
claude mcp add --transport sse github http://localhost:8000/sse
```

For private repositories, the token must have the required repository
permissions (including contents read/write for file operations and issues write
for issue creation). GitHub API errors are returned to Claude with their status
and message; keep the token private and provide it through the environment.
