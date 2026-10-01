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
