# Arquitectura del Sistema — Homelab
> Última actualización: 2026-03-23

---

## Servidores

| Servidor | IP Local | IP Tailscale | Rol |
|----------|----------|--------------|-----|
| **244** | `192.168.1.244` | `100.112.16.115` | Ingesta de datos + GLPI Proxy |
| **33** | `192.168.1.33` | `100.105.152.56` | AlgoTrading + GLPI Server |

---

## Diagrama General

```mermaid
graph LR

    subgraph EXT["External Sources"]
        MAE["MAE"]
        MATRIZ["Matriz / MatbaRofex"]
        BYMA["BYMA"]
        BINANCE["Binance"]
        YAHOO["Yahoo Finance"]
        NASDAQ["NASDAQ"]
    end

    subgraph P_SERVER["PROJECT: Server · 100.112.16.115"]
        direction TB

        subgraph SVC244["Ingestion Services"]
            WS["wsclient.service\nMatriz ticks"]
            BM["binance_monitor.service\nBinance klines"]
            OS["order_side.py\ncrontab · every 2min"]
        end

        subgraph DB244["Databases"]
            PG["PostgreSQL :5432\nticks · orders · binance_ticks"]
            MYSQL["MySQL :3306\nmarket_data OHLCV"]
        end

        MCP244["MCP + Hooks"]
    end

    subgraph P_GLPI["PROJECT: GLPI-API"]
        direction TB
        PROXY["GLPI Proxy :8080\n@ 100.112.16.115"]
        GLPI["GLPI Server :80\n@ 100.105.152.56"]
    end

    subgraph P_ALGO["PROJECT: AlgoTrading · 100.105.152.56"]
        direction TB

        subgraph TRADING["Trading"]
            RUNNER["live-crypto-runner\nevery 60s"]
            POLLER["db-poller\npolls DB 244 → :8004"]
            INGEST["ingestion FastAPI\n:8000"]
            RMQ["RabbitMQ\n:5672"]
        end

        subgraph OBS["Observability"]
            PUSH["Pushgateway :9091"]
            PROM["Prometheus :9090"]
            GRAFANA["Grafana :3000"]
        end

        MCP33["MCP + Hooks"]
    end

    subgraph CICD["GitHub CI/CD"]
        GH1["server repo"]
        GH2["AlgoTrading repo"]
        GH3["GLPI-API repo"]
    end

    %% External → Ingestion
    MAE & BYMA & NASDAQ & YAHOO -->|REST| WS
    MATRIZ -->|WebSocket| WS
    MATRIZ -->|REST poll| OS
    BINANCE -->|WebSocket| BM
    BINANCE -->|WebSocket| INGEST

    %% Ingestion → DB
    WS --> PG & MYSQL
    BM & OS --> PG

    %% Cross-server: 244 DB → 33
    PG -->|":5432"| POLLER & RUNNER & INGEST & GRAFANA
    MYSQL -->|":3306"| INGEST

    %% AlgoTrading internal
    INGEST --> RMQ
    RUNNER & POLLER & INGEST --> PUSH
    PUSH --> PROM --> GRAFANA

    %% GLPI ticket flow
    MCP244 & MCP33 -->|"create / close ticket"| PROXY
    PROXY -->|"HTTP :80"| GLPI

    %% CI/CD
    GH1 -->|deploy| P_SERVER
    GH2 -->|deploy| P_ALGO
    GH3 -->|deploy| P_GLPI
```

---

## Flujo de Datos

```mermaid
sequenceDiagram
    participant EXT as External Sources
    participant S244 as Server 100.112.16.115
    participant PG as PostgreSQL (100.112.16.115)
    participant S33 as AlgoTrading (100.105.152.56)
    participant PROM as Prometheus (100.105.152.56)
    participant GRAFANA as Grafana (100.105.152.56)

    Note over EXT,S244: Mon–Fri 10:00–17:00 ART

    EXT->>S244: WebSocket ticks (Matriz, Binance)
    EXT->>S244: REST poll every 2min (orders)
    S244->>PG: INSERT ticks / orders / binance_ticks

    S33->>PG: SELECT via SQLAlchemy pool (1–5 conns)
    PG-->>S33: market data

    S33->>S33: run strategies every 60s
    S33->>PROM: push metrics (Pushgateway :9091)
    S33->>PROM: expose DB gauges (db-poller :8004)
    PG->>GRAFANA: direct datasource (candlesticks)
    PROM->>GRAFANA: datasource
```

---

## Flujo GLPI (Tickets)

```mermaid
sequenceDiagram
    participant MCP244 as MCP + Hooks (100.112.16.115)
    participant MCP33 as MCP + Hooks (100.105.152.56)
    participant PROXY as GLPI Proxy :8080 (100.112.16.115)
    participant GLPI as GLPI Server :80 (100.105.152.56)

    MCP244->>PROXY: POST /token (OAuth)
    PROXY->>GLPI: forward → access_token
    MCP244->>PROXY: POST /Assistance/Ticket (create)
    PROXY->>GLPI: forward → ticket created

    MCP33->>PROXY: POST /token (OAuth)
    MCP33->>PROXY: POST /Assistance/Ticket (create)
    PROXY->>GLPI: forward → ticket created

    Note over MCP244,MCP33: task completes

    MCP244->>PROXY: PATCH /Assistance/Ticket/{id} (close)
    MCP33->>PROXY: PATCH /Assistance/Ticket/{id} (close)
    PROXY->>GLPI: forward → ticket closed
```

---

## PROJECT: Server (100.112.16.115)

### Ingestion Services

| Service | Type | Schedule | Output |
|---------|------|----------|--------|
| `wsclient.service` | systemd timer | Mon–Fri 10:00–17:00 ART | `ticks` (Matriz WebSocket) |
| `wsclient-stop.service` | systemd timer | Mon–Fri 17:00 ART | stops wsclient |
| `binance_monitor.service` | systemd timer | Mon–Fri 10:00–17:00 ART | `binance_ticks` |
| `order_side.py` | crontab `*/2` | Mon–Fri 10:00–17:00 ART | `orders` (Matriz REST) |

### Databases

| Engine | DB | Port | Tables |
|--------|----|------|--------|
| PostgreSQL 12 + TimescaleDB | `marketdata` | 5432 | `ticks` ~11.6M · `orders` ~144K · `binance_ticks` ~14K |
| MySQL | `investments` | 3306 | `market_data` (OHLCV yfinance) |

### External Platforms

| Platform | Protocol | Auth |
|----------|----------|------|
| MAE | REST | Public |
| Matriz / MatbaRofex | WebSocket + REST | Cookie via Playwright |
| BYMA | REST POST | Static token |
| NASDAQ | REST | Public |
| Yahoo Finance | yfinance lib | None |
| Binance | WebSocket | API Key + Secret |

---

## PROJECT: GLPI-API

| Component | Host | Port |
|-----------|------|------|
| GLPI Proxy (FastAPI · OAuth · JSONL logs) | `100.112.16.115` | :8080 |
| GLPI Server (IT Asset Management v2.2) | `100.105.152.56` | :80 |

Both servers use MCP + Hooks to automatically open a GLPI ticket before a task starts and close it on completion, via the proxy at `100.112.16.115:8080`.

---

## PROJECT: AlgoTrading (100.105.152.56)

### Trading Services

| Service | Type | Port | Description |
|---------|------|------|-------------|
| `db-poller.service` | systemd | :8004 | polls DB 244 → Prometheus gauges |
| `live-crypto-runner.service` | systemd | — | runs strategies every 60s |
| `algotrading-ingestion` | Docker | :8000/:8001/:8002 | FastAPI ingest + metrics |
| `algotrading-rabbitmq` | Docker | :5672/:15672 | message broker |
| `algotrading-binance-monitor` | Docker | :8003 ⚠️ | Binance live monitor (not scraped) |

### Observability Stack

| Service | Type | Port | Status |
|---------|------|------|--------|
| `algotrading-prometheus` | Docker | :9090 | ✅ |
| `algotrading-grafana` | Docker | :3000 | ✅ |
| `algotrading-pushgateway` | Docker | :9091 | ✅ |
| `algotrading-rabbitmq-exporter` | Docker | :9419 | ✅ |

### Prometheus Scrape Jobs

| Job | Target | Status |
|-----|--------|--------|
| `algotrading-ingestion` | `ingestion:8001` | ✅ |
| `algotrading-backtest` | `ingestion:8002` | ✅ |
| `algotrading-db-poller` | `host.docker.internal:8004` | ✅ |
| `pushgateway` | `pushgateway:9091` | ✅ |
| `rabbitmq` | `rabbitmq-exporter:9419` | ✅ |
| `algotrading-binance` | `binance-monitor:8003` | ❌ down |

### Grafana Dashboards

| Dashboard | Datasource | Shows |
|-----------|-----------|-------|
| Backtest Results | Prometheus | Return · Sharpe · Win rate · live P&L |
| Ingestion | Prometheus | DB 244 row counts · ticks last 5min |
| OHLCV | PostgreSQL direct | Candlestick 1h BTCUSDT + USDTARS |
| RabbitMQ | Prometheus | Queue depth · message rates |

### Active Strategies

| ID | File | Instruments | Logic |
|----|------|-------------|-------|
| BT-10 | `ppi_ohlcv_backtest.py` | 36 PPI tickers | MA / RSI / Bollinger |
| BT-11 | `options_backtest.py` | GGAL options | Black-Scholes long/short |
| BT-12 | `bt12_extended.py` | 36 tickers + BTCUSDT/USDTARS 1h | MACD / Stoch / ATR / Momentum |
| BT-14 | `live_rsi.py` | BTCUSDT live | RSI mean-reversion |

---

## Cross-Server Communication

| Connection | Protocol | Direction | Purpose |
|-----------|----------|-----------|---------|
| 100.105.152.56 → 100.112.16.115:5432 | PostgreSQL TCP | Pull | market data for strategies + Grafana |
| 100.105.152.56 → 100.112.16.115:3306 | MySQL TCP | Pull | OHLCV yfinance |
| 100.112.16.115 → 100.105.152.56:80 | HTTP | Push | GLPI Proxy → GLPI Server |
| 100.112.16.115/100.105.152.56 → 100.112.16.115:8080 | HTTP | Push | MCP+Hooks → GLPI Proxy |

---

## Instrument Naming

| Prefix | Market | Example |
|--------|--------|---------|
| `M:bm_MERV_` | BYMA equities/bonds | `M:bm_MERV_AL30_24hs` |
| `M:rx_DDF_DLR_` | MatbaRofex FX futures | `M:rx_DDF_DLR_MAR26` |
| `BTCUSDT` / `USDTARS` | Binance crypto | — |

> Active futures contract changes monthly — always query dynamically, never hardcode.

---

## Known Issues

| Issue | Impact | Priority |
|-------|--------|----------|
| `algotrading-binance` Prometheus target ❌ down | Low — data from db-poller | Low |
| `finance/PPI/` root has legacy duplicates | Import confusion | Medium |
| `live_rsi.py` duplicates `bt12_extended.py` logic | Tech debt | Medium |
| RabbitMQ consumer in ingestion incomplete (BT-15) | Binance→RMQ→DB flow broken | Medium |
| No backup strategy documented | Data loss risk | High |
| UFW inactive on proxy server | Security risk | High |

---

## Roadmap

| Task | Priority | Effort |
|------|----------|--------|
| Redis cache for market data (TTL 5s) | High | 8h |
| Complete BT-15: RabbitMQ consumer in ingestion | Medium | 4h |
| DB indexes on `(instrument, timestamp)` | Medium | 2h |
| Clean legacy duplicates in `finance/PPI/` | Medium | 2h |
| Unify `live_rsi.py` with `bt12_extended.py` | Medium | 4h |
| Document backup strategy | High | 3h |
| Enable UFW on proxy server | High | 1h |
| Test coverage → 60% | Medium | 12h |
