"""
Smoke tests for the MCP registry.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch


def test_agent_tools_are_defined():
    from agent.core import AGENT_TOOLS
    assert isinstance(AGENT_TOOLS, list)
    assert len(AGENT_TOOLS) > 0
    for tool in AGENT_TOOLS:
        assert "name" in tool
        assert "description" in tool


def test_register_agent_tools_registers_all_tools():
    with (
        patch("devops_mcp.registry.FastMCP"),
        patch("devops_mcp.registry.DevOpsAgent"),
    ):
        from agent.core import AGENT_TOOLS
        from devops_mcp.registry import register_agent_tools

        mock_mcp = MagicMock()
        mock_agent = MagicMock()
        register_agent_tools(mock_mcp, mock_agent)

        assert mock_mcp.add_tool.call_count == len(AGENT_TOOLS)
        registered_names = {
            call[1]["name"] for call in mock_mcp.add_tool.call_args_list
        }
        expected_names = {tool["name"] for tool in AGENT_TOOLS}
        assert registered_names == expected_names
