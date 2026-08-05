"""
DevOps AI Agent MCP Server

Exposes DevOps remediation tools, incident queue APIs, and org docs to any MCP client
(Cursor, Claude Desktop, custom agents, etc.) — not only the built-in agent loop.

Usage:
    devops-agent mcp                    # stdio (Cursor / Claude Desktop)
    devops-agent mcp --transport sse --port 8090
"""
from __future__ import annotations

import os

import structlog
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from agent.core import AGENT_TOOLS, DevOpsAgent
from devops_mcp.registry import register_agent_tools, register_platform_tools, register_resources
from services.incident_queue import IncidentQueue
from services.incident_store import IncidentStore
from services.org_config import OrgConfig
from services.org_docs import OrgDocs

load_dotenv()
log = structlog.get_logger()

INSTRUCTIONS = """\
DevOps AI Agent MCP — infrastructure incident response for any AI agent.

**Bring your own keys (BYOK):** Each org uses their own Anthropic, Slack, GitHub,
kube, and cloud credentials — configure them in your MCP env block or via
configure_org_credentials. The platform operator should not supply org secrets.

Use individual tools (get_k8s_context, get_github_logs, run_kubectl, etc.) to gather
context and apply safe remediations. Use enqueue_incident to queue work for the
background worker, or diagnose_incident to run the full Claude agent loop with your org's API key.

Org runbooks: list_org_docs / get_org_doc. Audit history: get_incident_audit.
"""


def create_mcp_server() -> FastMCP:
    mcp = FastMCP(
        name="devops-ai-agent",
        instructions=INSTRUCTIONS,
    )

    agent = DevOpsAgent()
    incident_queue = IncidentQueue()
    incident_store = IncidentStore()
    org_docs = OrgDocs()
    org_config = OrgConfig()

    register_agent_tools(mcp, agent)
    register_platform_tools(mcp, agent, incident_queue, incident_store, org_docs, org_config)
    register_resources(mcp, incident_store, org_docs)

    log.info(
        "DevOps MCP server initialized",
        tools=len(AGENT_TOOLS) + 8,
        org_id=os.getenv("ORG_ID", "default"),
    )
    return mcp


def run_mcp(
    transport: str = "stdio",
    host: str | None = None,
    port: int | None = None,
) -> None:
    mcp = create_mcp_server()

    if transport == "stdio":
        mcp.run(transport="stdio")
        return

    if transport in ("sse", "streamable-http"):
        # Explicit host/port beat the environment; FASTMCP_HOST/FASTMCP_PORT
        # (e.g. from .env) supply the value only when no flag was passed.
        if host is not None:
            os.environ["FASTMCP_HOST"] = host
        else:
            os.environ.setdefault("FASTMCP_HOST", "127.0.0.1")
        if port is not None:
            os.environ["FASTMCP_PORT"] = str(port)
        else:
            os.environ.setdefault("FASTMCP_PORT", "8090")
        mcp.run(transport=transport)
        return

    raise ValueError(f"Unknown transport: {transport}. Use stdio, sse, or streamable-http.")


if __name__ == "__main__":
    run_mcp()
