# GLPI API Proxy

Intermediate proxy layer for centralizing communication with the GLPI v2.2 API. Handles OAuth authentication, full request/response logging, and transparent request forwarding.

- **Stack**: Python 3.10+ / FastAPI / httpx
- **Default port**: `8080`
- **Target GLPI server**: configurable via `GLPI_API_URL`

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Description | Example |
|---|---|---|
| `GLPI_API_URL` | Base URL of the GLPI server | `http://192.168.1.33:80` |
| `GLPI_CLIENT_ID` | OAuth client ID | `ad656bf9...` |
| `GLPI_CLIENT_SECRET` | OAuth client secret | `415ade76...` |
| `GLPI_USERNAME` | GLPI user | `admin` |
| `GLPI_PASSWORD` | GLPI password | `secret` |
| `PROXY_HOST` | Bind address | `0.0.0.0` |
| `PROXY_PORT` | Proxy port | `8080` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_DIR` | Log output directory | `./logs` |
| `HTTP_TIMEOUT` | HTTP timeout in seconds | `30` |

### 3. Run

```bash
python -m app.main
```

Interactive docs available at `http://localhost:8080/docs`.

---

## Endpoints

All endpoints are prefixed with `/api/v2.2`.

### `GET /`

Service info.

**Response**
```json
{
  "service": "GLPI API Proxy",
  "version": "1.0.0",
  "status": "running",
  "docs": "/docs",
  "health": "/api/v2.2/Health",
  "glpi_server": "http://192.168.1.33:80"
}
```

---

### `POST /api/v2.2/token`

Obtain an OAuth Bearer token using the Password Grant flow. Accepts both `application/json` and `application/x-www-form-urlencoded`.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `grant_type` | string | yes | Must be `"password"` |
| `client_id` | string | yes | OAuth client ID (must match `GLPI_CLIENT_ID`) |
| `client_secret` | string | yes | OAuth client secret (must match `GLPI_CLIENT_SECRET`) |
| `username` | string | yes | GLPI username |
| `password` | string | yes | GLPI password |

**Example (JSON)**
```bash
curl -X POST http://localhost:8080/api/v2.2/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "password",
    "client_id": "<your_client_id>",
    "client_secret": "<your_client_secret>",
    "username": "<glpi_user>",
    "password": "<glpi_password>"
  }'
```

**Example (form-urlencoded)**
```bash
curl -X POST http://localhost:8080/api/v2.2/token \
  -d "grant_type=password&client_id=<id>&client_secret=<secret>&username=<user>&password=<pass>"
```

**Response `200`**
```json
{
  "access_token": "eyJ...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "scope": null
}
```

**Error responses**

| Code | Reason |
|---|---|
| `400` | `grant_type` is not `"password"` |
| `401` | Invalid `client_id`, `client_secret`, or user credentials |
| `422` | Missing required fields |

---

### `GET /api/v2.2/Health`

Returns the health status of the proxy and its connection to GLPI.

**Response `200`**
```json
{
  "status": "healthy",
  "service": "glpi-api-proxy",
  "version": "1.0.0",
  "glpi_connected": true,
  "token_valid": true
}
```

`status` is `"healthy"` when GLPI is reachable, `"degraded"` otherwise.  
`token_valid` is `null` if no token has been obtained yet.

---

### `GET /api/v2.2/ping`

Lightweight liveness check.

**Response `200`**
```json
{
  "service": "glpi-api-proxy",
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `* /api/v2.2/{resource}`

Generic proxy to any GLPI endpoint. Supports `GET`, `POST`, `PUT`, `DELETE`, `PATCH`.

The `{resource}` path is forwarded to GLPI as `/api.php/v2.2/{resource}`, preserving the original method, query parameters, and body.

**Required header**

```
Authorization: Bearer <access_token>
```

If the header is omitted and a valid token is cached in memory, the proxy will use it automatically. Otherwise a `401` is returned.

**Example — list users**
```bash
curl http://localhost:8080/api/v2.2/Administration/User \
  -H "Authorization: Bearer <token>"
```

**Example — create a ticket**
```bash
curl -X POST http://localhost:8080/api/v2.2/Assistance/Ticket \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Printer not working", "content": "..."}'
```

**Error responses**

| Code | Reason |
|---|---|
| `401` | No token provided and no valid cached token |
| `502` | Could not reach the GLPI server |

---

## Headers forwarded to GLPI

Every upstream request automatically includes:

| Header | Value |
|---|---|
| `Accept` | `application/json` |
| `GLPI-Entity-Recursive` | `true` |
| `Accept-Language` | `en_GB` |
| `Authorization` | `Bearer <token>` |

---

## Logging

All requests and responses are logged to `./logs/requests.jsonl` (configurable via `LOG_DIR`) in JSON Lines format.

Each entry has the following shape:

```json
{
  "timestamp": "2026-03-14T12:00:00.000Z",
  "request_id": "uuid-v4",
  "type": "input|output|error",
  "direction": "client_to_proxy|proxy_to_glpi|glpi_to_proxy|proxy_to_client",
  "method": "GET",
  "path": "/api/v2.2/Administration/User",
  "headers": { "Authorization": "Bearer eyJ***" },
  "body": null,
  "status_code": 200,
  "response_time_ms": 142,
  "source_ip": "192.168.1.100",
  "error": null
}
```

Sensitive headers (`Authorization`, `password`, `client_secret`, etc.) are masked automatically. Each HTTP response also includes an `X-Request-ID` header with the corresponding log entry ID.

Log files rotate daily and are retained for 30 days.

---

## Recent Changes

| Commit | Description |
|---|---|
| `65e32ae` | `/token` endpoint now accepts both JSON and form-urlencoded bodies |
| `b5193b8` | Fixed `X-Request-ID` header being set correctly after response rebuild |
| `a08a3a5` | Removed hardcoded URL in `proxy.py`; now uses `settings.glpi_api_url` |
| `a8458ca` | Fixed middleware not capturing full response body |
| `e2940cf` | Added test environment setup script (`setup_test_env.sh`) |
| `5bd2e7b` | Initial implementation: proxy, OAuth, logging middleware |

---

## Project Structure

```
glpi-api/
├── app/
│   ├── main.py              # FastAPI app, middleware registration
│   ├── config.py            # Settings (pydantic-settings, .env)
│   ├── models/
│   │   ├── token.py         # TokenRequest, TokenResponse, TokenData
│   │   └── requests.py      # HealthResponse, LogEntry, ProxyRequest
│   ├── services/
│   │   ├── oauth.py         # OAuthManager — token lifecycle
│   │   ├── glpi_client.py   # GLPIClient — HTTP client for GLPI
│   │   └── logger.py        # ProxyLogger — JSONL logging
│   ├── routes/
│   │   ├── token.py         # POST /token
│   │   ├── health.py        # GET /Health, GET /ping
│   │   └── proxy.py         # Catch-all proxy handler
│   └── middleware/
│       └── logging.py       # Request/response logging middleware
├── logs/                    # JSONL log output
├── .env.example
├── requirements.txt
├── SPEC.md
└── setup_test_env.sh
```
