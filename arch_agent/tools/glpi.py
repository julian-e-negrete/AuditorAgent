"""GLPITool — async wrapper around the GLPI proxy at settings.GLPI_PROXY_URL."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from arch_agent.config import Settings
from arch_agent.exceptions import GLPIUnavailableError
from arch_agent.models.glpi import Ticket

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0


def _mask(value: str) -> str:
    """Return *** for any non-empty string (used to mask secrets in logs)."""
    return "***" if value else value


class GLPITool:
    """Async GLPI ticket client.

    Authenticates via OAuth (password grant) against the GLPI server and
    communicates with the proxy at *proxy_url*.  The OAuth token is kept
    in memory only — never written to disk.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings: Settings = settings or Settings()  # type: ignore[call-arg]
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _proxy_url(self) -> str:
        return self._settings.GLPI_PROXY_URL.rstrip("/")

    def _server_name(self) -> str:
        return self._settings.GLPI_SERVER_NAME

    async def _authenticate(self, client: httpx.AsyncClient) -> None:
        """Fetch a fresh OAuth token and store it in memory."""
        proxy_url = self._proxy_url()
        data = {
            "grant_type": "password",
            "client_id": self._settings.GLPI_CLIENT_ID,
            "client_secret": self._settings.GLPI_CLIENT_SECRET,
            "username": self._settings.GLPI_USERNAME,
            "password": self._settings.GLPI_PASSWORD,
            "scope": "api user",
        }
        logger.debug(
            "Authenticating with GLPI proxy — client_id=%s client_secret=%s",
            self._settings.GLPI_CLIENT_ID,
            _mask(self._settings.GLPI_CLIENT_SECRET),
        )
        try:
            resp = await client.post(
                f"{proxy_url}/api.php/token",
                data=data,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GLPIUnavailableError(f"GLPI proxy unreachable during auth: {exc}") from exc

        self._token = resp.json()["access_token"]

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _log_request(self, method: str, url: str, headers: dict[str, str]) -> None:
        safe_headers = {
            k: (_mask(v) if k.lower() == "authorization" else v)
            for k, v in headers.items()
        }
        logger.debug("%s %s headers=%s", method, url, safe_headers)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute a request, re-authenticating once on 401."""
        if self._token is None:
            await self._authenticate(client)

        headers = self._auth_headers()
        self._log_request(method, url, headers)

        try:
            resp = await client.request(
                method, url, headers=headers, timeout=_TIMEOUT, **kwargs
            )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GLPIUnavailableError(f"GLPI proxy unreachable: {exc}") from exc

        if resp.status_code == 401:
            # Re-authenticate once and retry
            await self._authenticate(client)
            headers = self._auth_headers()
            self._log_request(method, url, headers)
            try:
                resp = await client.request(
                    method, url, headers=headers, timeout=_TIMEOUT, **kwargs
                )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                raise GLPIUnavailableError(f"GLPI proxy unreachable on retry: {exc}") from exc

        return resp

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_server_ticket(
        self,
        title: str,
        description: str,
        agent: str = "kiro",
        urgency: int = 3,
    ) -> int:
        """Create a ticket linked to the configured server.

        Returns the positive integer ticket ID.
        Raises GLPIUnavailableError on network failure.
        """
        url = f"{self._proxy_url()}/api/v2.2/infra/servers/{self._server_name()}/tickets"
        payload = {
            "title": title,
            "description": description,
            "agent": agent,
            "urgency": urgency,
        }
        async with httpx.AsyncClient() as client:
            resp = await self._request(client, "POST", url, json=payload)
        resp.raise_for_status()
        ticket_id: int = resp.json()["id"]
        return ticket_id

    async def complete_server_ticket(
        self,
        ticket_id: int,
        solution: str = "Tarea completada por agente.",
    ) -> None:
        """Mark a ticket as solved.

        Raises GLPIUnavailableError on network failure.
        """
        url = (
            f"{self._proxy_url()}/api/v2.2/infra/servers/"
            f"{self._server_name()}/tickets/{ticket_id}/complete"
        )
        async with httpx.AsyncClient() as client:
            resp = await self._request(client, "PATCH", url, json={"solution": solution})
        resp.raise_for_status()

    async def list_server_tickets(self) -> list[Ticket]:
        """Return all active tickets for the configured server.

        Raises GLPIUnavailableError on network failure.
        """
        url = f"{self._proxy_url()}/api/v2.2/infra/servers/{self._server_name()}/tickets"
        async with httpx.AsyncClient() as client:
            resp = await self._request(client, "GET", url)
        resp.raise_for_status()

        tickets: list[Ticket] = []
        for item in resp.json():
            tickets.append(
                Ticket(
                    id=item["id"],
                    title=item["title"],
                    content=item.get("content", ""),
                    status=item["status"],
                    urgency=item["urgency"],
                )
            )
        return tickets
