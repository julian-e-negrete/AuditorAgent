"""Unit tests for GLPITool using unittest.mock to patch httpx.AsyncClient."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arch_agent.exceptions import GLPIUnavailableError
from arch_agent.tools.glpi import GLPITool
import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    """Return a minimal Settings-like object without touching the real .env."""
    defaults = dict(
        LLM_PROVIDER="openai",
        LLM_API_KEY="test-key",
        GLPI_PROXY_URL="http://proxy.test:8080",
        GLPI_CLIENT_ID="client-id",
        GLPI_CLIENT_SECRET="client-secret",
        GLPI_USERNAME="user",
        GLPI_PASSWORD="pass",
        GLPI_SERVER_NAME="SRV-TEST",
    )
    defaults.update(overrides)

    class FakeSettings:
        pass

    s = FakeSettings()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def _mock_response(status_code: int, body: dict | list) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _build_client_mock(responses: list) -> MagicMock:
    """Build an AsyncClient context-manager mock that returns *responses* in order."""
    client = MagicMock()
    client.request = AsyncMock(side_effect=responses)
    client.post = AsyncMock(side_effect=responses)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateServerTicket:
    @pytest.mark.asyncio
    async def test_returns_positive_int_on_success(self):
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        tool._token = "valid-token"  # skip auth

        ticket_resp = _mock_response(200, {"id": 42})

        cm, client = _build_client_mock([ticket_resp])
        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            result = await tool.create_server_ticket("My title", "My description")

        assert isinstance(result, int)
        assert result > 0
        assert result == 42

    @pytest.mark.asyncio
    async def test_raises_on_network_error(self):
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        tool._token = "valid-token"

        cm, client = _build_client_mock([httpx.ConnectError("refused")])
        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            with pytest.raises(GLPIUnavailableError):
                await tool.create_server_ticket("title", "desc")

    @pytest.mark.asyncio
    async def test_reauth_on_401(self):
        """On a 401 the tool should re-authenticate and retry."""
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        tool._token = "expired-token"

        token_resp = _mock_response(200, {"access_token": "new-token"})
        unauth_resp = _mock_response(401, {"error": "unauthorized"})
        unauth_resp.raise_for_status = MagicMock()  # don't raise on 401 — tool handles it
        ticket_resp = _mock_response(200, {"id": 7})

        # client.request is called for the actual API calls
        # client.post is called for the token endpoint
        client = MagicMock()
        client.request = AsyncMock(side_effect=[unauth_resp, ticket_resp])
        client.post = AsyncMock(return_value=token_resp)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            result = await tool.create_server_ticket("title", "desc")

        assert result == 7
        assert tool._token == "new-token"


class TestCompleteServerTicket:
    @pytest.mark.asyncio
    async def test_completes_successfully(self):
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        tool._token = "valid-token"

        ok_resp = _mock_response(200, {"status": "ok"})
        cm, client = _build_client_mock([ok_resp])

        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            result = await tool.complete_server_ticket(42)

        assert result is None

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        tool._token = "valid-token"

        cm, client = _build_client_mock([httpx.TimeoutException("timeout")])
        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            with pytest.raises(GLPIUnavailableError):
                await tool.complete_server_ticket(42)


class TestListServerTickets:
    @pytest.mark.asyncio
    async def test_returns_list_of_ticket_objects(self):
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        tool._token = "valid-token"

        raw = [
            {
                "id": 1,
                "title": "Ticket A",
                "content": "desc A",
                "status": "new",
                "urgency": 2,
            },
            {
                "id": 2,
                "title": "Ticket B",
                "content": "desc B",
                "status": "processing",
                "urgency": 3,
            },
        ]
        list_resp = _mock_response(200, raw)
        cm, client = _build_client_mock([list_resp])

        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            tickets = await tool.list_server_tickets()

        assert len(tickets) == 2
        assert tickets[0].id == 1
        assert tickets[0].title == "Ticket A"
        assert tickets[1].status == "processing"

    @pytest.mark.asyncio
    async def test_raises_on_network_failure(self):
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        tool._token = "valid-token"

        cm, client = _build_client_mock([httpx.ConnectError("unreachable")])
        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            with pytest.raises(GLPIUnavailableError):
                await tool.list_server_tickets()


class TestOAuthAuthentication:
    @pytest.mark.asyncio
    async def test_authenticates_when_no_token(self):
        """GLPITool should fetch a token automatically when _token is None."""
        settings = _make_settings()
        tool = GLPITool(settings=settings)
        # _token is None by default

        token_resp = _mock_response(200, {"access_token": "fresh-token"})
        ticket_resp = _mock_response(200, {"id": 99})

        client = MagicMock()
        client.post = AsyncMock(return_value=token_resp)
        client.request = AsyncMock(return_value=ticket_resp)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            result = await tool.create_server_ticket("title", "desc")

        assert result == 99
        assert tool._token == "fresh-token"

    @pytest.mark.asyncio
    async def test_auth_network_failure_raises(self):
        """Network error during auth should raise GLPIUnavailableError."""
        settings = _make_settings()
        tool = GLPITool(settings=settings)

        client = MagicMock()
        client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("arch_agent.tools.glpi.httpx.AsyncClient", return_value=cm):
            with pytest.raises(GLPIUnavailableError):
                await tool.create_server_ticket("title", "desc")
