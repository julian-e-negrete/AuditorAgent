"""
GLPI API Proxy — MCP bridge para AlgoTrading.
Expone herramientas para crear, listar y completar tickets en GLPI
a través del proxy corriendo en SRV-SCRAPING-PROXY.
"""
import json
import httpx
from mcp.server.fastmcp import FastMCP

PROXY_URL = "http://100.112.16.115"
GLPI_URL = "http://100.105.152.56"
CLIENT_ID = "5880211c5e72134f1ae47dda08377e4b503bd3d15f93d858dda5ab82a4a000e0"
CLIENT_SECRET = "b6d8fbdc08f6443abce916dae0d5184f56793a50782130e3c6fa6153692d165c"
USERNAME = "HaraiDasan"
PASSWORD = "45237348"
SERVER_NAME = "SRV-GLPI-PROCESSOR"

mcp = FastMCP("glpi-api-proxy")


def _get_token() -> str:
    r = httpx.post(
        f"{GLPI_URL}/api.php/token",
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "username": USERNAME,
            "password": PASSWORD,
            "scope": "api user",
        },
        timeout=15,
    )
    return r.json()["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


@mcp.tool()
def proxy_health() -> str:
    """Verifica el estado del proxy GLPI y su conexión con GLPI."""
    try:
        r = httpx.get(f"{PROXY_URL}/api/v2.2/Health", timeout=10)
        return json.dumps(r.json(), ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def create_server_ticket(title: str, description: str, agent: str = "kiro", urgency: int = 3) -> str:
    """
    Crea un ticket en GLPI vinculado a SRV-GLPI-PROCESSOR.
    Usar al iniciar una tarea para registrarla en GLPI.
    urgency: 1=muy alta, 2=alta, 3=media, 4=baja, 5=muy baja
    """
    try:
        r = httpx.post(
            f"{PROXY_URL}/api/v2.2/infra/servers/{SERVER_NAME}/tickets",
            headers=_headers(),
            json={"title": title, "description": description, "agent": agent, "urgency": urgency},
            timeout=15,
        )
        return json.dumps(r.json(), ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def list_server_tickets() -> str:
    """Lista todos los tickets activos de SRV-GLPI-PROCESSOR en GLPI."""
    try:
        r = httpx.get(
            f"{PROXY_URL}/api/v2.2/infra/servers/{SERVER_NAME}/tickets",
            headers={"Authorization": f"Bearer {_get_token()}"},
            timeout=15,
        )
        return json.dumps(r.json(), ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def complete_server_ticket(ticket_id: int, solution: str = "Tarea completada por agente.") -> str:
    """
    Marca un ticket de SRV-GLPI-PROCESSOR como resuelto.
    Usar al finalizar una tarea para cerrar el ticket en GLPI.
    """
    try:
        r = httpx.patch(
            f"{PROXY_URL}/api/v2.2/infra/servers/{SERVER_NAME}/tickets/{ticket_id}/complete",
            headers=_headers(),
            json={"solution": solution},
            timeout=15,
        )
        try:
            return json.dumps(r.json(), ensure_ascii=False)
        except Exception:
            return json.dumps({"status": r.status_code, "body": r.text or "ok"})
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
