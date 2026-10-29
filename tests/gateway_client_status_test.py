"""Workspace presentation tests for gateway MCP startup states."""

import asyncio
import json
from unittest.mock import AsyncMock

from agentscope.app._router._workspace import list_mcps
from agentscope.mcp import MCPClient
from agentscope.workspace._gateway_client import (
    GatewayClient,
    MCPNotReadyError,
)


def _gateway_client(status: int, payload: dict) -> tuple[MCPClient, AsyncMock]:
    gateway = AsyncMock(spec=GatewayClient)
    gateway.exec_request.return_value = status, json.dumps(payload).encode()
    client = GatewayClient.make_client(
        gateway,
        MCPClient(
            name="maps",
            is_stateful=True,
            mcp_config={"type": "stdio_mcp", "command": "maps"},
        ).model_dump(mode="json"),
        agent_id="agent",
        session_id="session",
        connected=True,
    )
    return client, gateway


def _list_workspace(client: MCPClient):
    workspace = AsyncMock()
    workspace.list_mcps.return_value = [client]
    service = AsyncMock()
    service.resolve.return_value = workspace
    return asyncio.run(
        list_mcps(
            agent_id="agent",
            session_id="session",
            user_id="user",
            workspace_service=service,
        ),
    )[0]


def test_gateway_client_classifies_not_ready_conflict() -> None:
    """Only the gateway's temporary 409 gets a dedicated exception."""
    client, _ = _gateway_client(
        409,
        {"error": {"code": "mcp_not_ready", "message": "Starting"}},
    )

    try:
        asyncio.run(client.list_tools())
    except MCPNotReadyError:
        pass
    else:
        raise AssertionError("409 mcp_not_ready was not classified")


def test_workspace_hides_temporary_not_ready_error() -> None:
    """A starting MCP exposes status without rendering an error message."""
    client, gateway = _gateway_client(
        409,
        {"error": {"code": "mcp_not_ready", "message": "Starting"}},
    )

    result = _list_workspace(client)

    assert result.status == "starting"
    assert result.is_healthy is False
    assert result.error is None
    assert gateway.exec_request.await_count == 1


def test_workspace_reports_non_409_errors() -> None:
    """Authentication, startup and transport failures remain visible."""
    client, _ = _gateway_client(
        502,
        {"error": {"code": "mcp_start_failed", "message": "HTTP 401 Unauthorized"}},
    )

    result = _list_workspace(client)

    assert result.status == "failed"
    assert result.is_healthy is False
    assert "401 Unauthorized" in result.error
