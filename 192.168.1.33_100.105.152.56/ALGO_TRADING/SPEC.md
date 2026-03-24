# AlgoTrading — System Specification

_Last updated: 2026-03-23_

---

## 0. System Audit — Current State (2026-03-23)

### Running Services

| Component | Type | Status | Uptime |
|-----------|------|--------|--------|
| `db-poller.service` | systemd | ✅ active | since 2026-03-22 23:21 UTC |
| `live-crypto-runner.service` | systemd | ✅ active | since 2026-03-22 22:55 UTC |
| `algotrading-ingestion` | Docker | ✅ up | 24h+ |
| `algotrading-prometheus` | Docker | ✅ up | — |
| `algotrading-grafana` | Docker | ✅ up | 24h+ |
| `algotrading-pushgateway` | Docker | ✅ up | — |
| `algotrading-rabbitmq` | Docker | ✅ up | 30h+ |
| `algotrading-rabbitmq-exporter` | Docker | ✅ up | — |
| `algotrading-binance-monitor` | Docker | ⚠️ up, :8003 not scraped | — |

### Prometheus Targets

| Job | Status | Notes |
|-----|--------|-------|
| `algotrading-db-poller` | ✅ up | `host.docker.internal:8004` |
| `algotrading-ingestion` | ✅ up | `ingestion:8001` |
| `algotrading-backtest` | ✅ up | `ingestion:8002` |
| `pushgateway` | ✅ up | `pushgateway:9091` |
| `rabbitmq` | ✅ up | `rabbitmq-exporter:9419` |
| `algotrading-binance` | ❌ down | Docker container not exposing :8003 to host |

### Grafana Dashboards

| Dashboard | UID | Data Source | Status |
|-----------|-----|-------------|--------|
| AlgoTrading — Backtest Results | `algotrading-backtest` | Prometheus | ✅ live positions + P&L |
| AlgoTrading — Ingestion | `algotrading-ingestion` | Prometheus | ✅ real DB row counts from 244 |
| AlgoTrading — OHLCV | `algotrading-ohlcv` | PostgreSQL | ✅ real 1h candlesticks |
| AlgoTrading — RabbitMQ | `algotrading-rabbitmq` | Prometheus | ✅ |

### Live Strategy State (last run)

| Symbol | Strategy | Position | Total Return |
|--------|----------|----------|-------------|
| BTCUSDT | crypto_rsi | LONG | +24.1% |
| BTCUSDT | crypto_bb | FLAT | +29.9% |
| BTCUSDT | crypto_macd | FLAT | +0.9% |
| BTCUSDT | crypto_momentum | SHORT | +3.0% |
| USDTARS | crypto_rsi | FLAT | +4.2% |
| USDTARS | crypto_macd | FLAT | +7.3% |
| USDTARS | crypto_bb | FLAT | -2.2% |
| USDTARS | crypto_momentum | FLAT | -1.5% |

### Database State (244)

| Table | Latest Row | Total Rows |
|-------|-----------|------------|
| `binance_ticks BTCUSDT` | 2026-03-23 00:56 UTC (live) | ~7,020 |
| `binance_ticks USDTARS` | 2026-03-23 00:56 UTC (live) | ~6,993 |
| `ticks` (AR market) | 2026-03-22 15:47 UTC | ~11.6M |
| `orders` | — | ~144K |
| `bt_strategy_runs` | — | crypto + historical |

### Known Issues

| Issue | Impact | Priority |
|-------|--------|----------|
| `algotrading-binance` Prometheus target down | Low — data comes from DB poller | Low |
| CHANGELOG has duplicate `[2026-03-22]` date headers | Cosmetic | Low |

---

## 1. Architecture Overview

```
Binance WS ──► AsyncBinanceMonitor ──► Prometheus :8003
                      │
                      ▼
              RabbitMQ exchange: market.ticks  (BT-15)
                      │
                      ▼
           Ingestion Service :8000/:8001
                      │
              ┌───────┴────────┐
              ▼                ▼
         PostgreSQL          MySQL
         (ticks,             (market_data
          binance_ticks,      OHLCV)
          bt_strategy_runs)
                      │
                      ▼
              Pushgateway :9091
                      │
              Prometheus :9090
                      │
               Grafana :3000
```

---

## 2. Services

| Service | Port | Purpose |
|---------|------|---------|
| ingestion | 8000 | FastAPI — tick/OHLCV ingest endpoints |
| ingestion metrics | 8001 | Prometheus metrics for ingestion |
| backtest metrics | 8002 | Prometheus metrics for backtest results |
| binance-monitor | 8003 | Prometheus metrics for live Binance stream |
| RabbitMQ | 5672 / 15672 | Message broker (market.ticks exchange) |
| Pushgateway | 9091 | Backtest result push |
| Prometheus | 9090 | Metrics scrape + TSDB |
| Grafana | 3000 | Dashboards |

---

## 3. Databases

### PostgreSQL `marketdata` @ `100.112.16.115:5432`

| Table | Type | Key columns |
|-------|------|-------------|
| `ticks` | hypertable | `time` UTC, `instrument`, bid/ask/last/volume |
| `orders` | hypertable | `time` UTC, `instrument`, `side`, `price`, `volume` |
| `binance_ticks` | hypertable | `symbol`, `timestamp` UTC, OHLCV |
| `bt_strategy_runs` | regular | `run_at`, `instrument`, `strategy`, metrics |

> `total_volume` in `ticks` is **cumulative daily** — volume per period = `MAX - MIN`.

### MySQL `investments` @ `100.112.16.115:3306`

| Table | Key columns |
|-------|-------------|
| `market_data` | `ticker`, `timestamp`, OHLCV |

---

## 4. Prometheus Metrics

### Ingestion (`:8001`)
| Metric | Type | Labels |
|--------|------|--------|
| `algotrading_ticks_ingested_total` | Counter | `instrument` |
| `algotrading_ohlcv_ingested_total` | Counter | `ticker` |
| `algotrading_ingest_errors_total` | Counter | `endpoint` |
| `algotrading_ingest_latency_seconds` | Histogram | `endpoint` |

### Backtest (`:8002` + Pushgateway)
| Metric | Type | Labels |
|--------|------|--------|
| `algotrading_backtest_runs_total` | Counter | `strategy` |
| `algotrading_backtest_total_return` | Gauge | `strategy`, `instrument` |
| `algotrading_backtest_sharpe` | Gauge | `strategy`, `instrument` |
| `algotrading_backtest_win_rate` | Gauge | `strategy`, `instrument` |
| `algotrading_backtest_profit_factor` | Gauge | `strategy`, `instrument` |

### Binance Monitor (`:8003`)
| Metric | Type | Labels |
|--------|------|--------|
| `algotrading_binance_ticks_total` | Counter | `symbol` |
| `algotrading_binance_close_price` | Gauge | `symbol` |
| `algotrading_binance_rsi` | Gauge | `symbol` |
| `algotrading_binance_volume` | Gauge | `symbol` |

---

## 5. Data Contracts

### Instrument Naming
| Prefix | Market | Example |
|--------|--------|---------|
| `M:bm_MERV_` | BYMA equities/bonds | `M:bm_MERV_AL30_24hs` |
| `M:rx_DDF_DLR_` | MatbaRofex FX futures | `M:rx_DDF_DLR_MAR26` |
| `BTCUSDT` / `USDTARS` | Binance crypto | — |
| `GGAL_options_YYYY-MM-DD` | BYMA options backtest | — |

### Timestamps
- All DB timestamps are **UTC**
- Convert to ART: `AT TIME ZONE 'America/Argentina/Buenos_Aires'`
- Market hours: 10:00–17:00 ART, Mon–Fri

### Backtest `total_return`
Always normalized: `sum(net_pnl) / sum(entry_price × CONTRACT_SIZE)`
Result is a decimal fraction (e.g. `0.0056`, not `560%`).

---

## 6. RabbitMQ Integration

Exchange: `market.ticks` (topic, durable)  
Routing key: `binance.<symbol>` (e.g. `binance.BTCUSDT`)  
Message format:
```json
{"symbol": "BTCUSDT", "timestamp": "2026-03-22T20:00:00Z",
 "open": 85000.0, "high": 85100.0, "low": 84900.0, "close": 85050.0, "volume": 12.5}
```
Consumer: ingestion service persists to `binance_ticks`.

---

## 7. CI/CD

### GitHub Actions
- `ci.yml` — runs on every push to `master`: pytest with 30% coverage gate
- `deploy.yml` — SSH deploy to host on push to `master` (skips `docs/**`, `*.md`)

### Known constraints
- Redis tests skip when Redis is unreachable (CI environment)
- Deploy requires `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` secrets in GitHub

---

## 8. Credentials

All via `finance.config.settings` (pydantic-settings from `.env`). Never hardcoded.

| Key group | Variables |
|-----------|-----------|
| PostgreSQL | `POSTGRES_HOST/PORT/USER/PASSWORD/DB` |
| MySQL | `DB_HOST/PORT/USER/PASSWORD/NAME` |
| Binance | `BINANCE_API_KEY`, `BINANCE_API_SECRET` |
| PPI | `PPI_PUBLIC_KEY`, `PPI_PRIVATE_KEY` |
| RabbitMQ | `RABBITMQ_USER`, `RABBITMQ_PASSWORD` |
| Redis | `REDIS_HOST`, `REDIS_PORT` |
