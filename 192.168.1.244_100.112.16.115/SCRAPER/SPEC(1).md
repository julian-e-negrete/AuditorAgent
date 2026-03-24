# SPEC.md — Spec Anchor
> Source of truth for the scraper/data-ingestion server.
> All code in this repo must reference a requirement defined here.

---

## 1. Target Platforms

| ID | Platform | Transport | Auth | Module(s) |
|----|----------|-----------|------|-----------|
| P1 | MAE (Mercado Abierto Electrónico) | REST (aiohttp) | None (public API) | `web_scraping/A3/dolar.py`, `caucion.py`, `RentaFija.py`, `horarioMercado.py`, `api/dolar.py` |
| P2 | MatbaRofex / Matriz (`matriz.eco.xoms.com.ar`) | WebSocket + REST | Cookie (`_mtz_web_key`) via Playwright headless login | `web_scraping/matriz/matrizwb.py`, `order_side.py`, `minutes_ticker.py`, `job/futuros_tick_by_tick.py`, `job/order_side.py`, `web_scraping/A3/web_socket/futuros_dolar.py`, `real_timeMep.py` |
| P3 | MatbaRofex Primary Ventures (`matbarofex.primary.ventures`) | WebSocket + REST | None (public WS) | `api/futuros_dolar.py`, `api/historical.py`, `web_scraping/A3/web_socket/futuros_dolar.py` |
| P4 | BYMA (`open.bymadata.com.ar`) | REST POST (aiohttp) | Static token header | `web_scraping/BYMA/leading_equity.py`, `cedears.py` |
| P5 | NASDAQ (`api.nasdaq.com`) | REST GET | None (public) | `web_scraping/NASDAQ/pbr.py` |
| P6 | Yahoo Finance / yfinance | yfinance lib (wraps Yahoo) | None | `yfinance_websocket/websocket_server.py`, `populate_intraday.py` |
| P7 | Binance | WebSocket (binance-python) | API Key + Secret | `monitor/data_stream.py` |

---

## 2. Data Contract

### 2.1 Databases

| DB Engine | Database Name | Host | Port | Used By |
|-----------|--------------|------|------|---------|
| MySQL | `investments` | `localhost` | 3306 | `yfinance_websocket/` |
| PostgreSQL | `marketdata` | `localhost` | 5432 | `job/`, `web_scraping/matriz/`, `monitor/` |

> Host unified to `localhost` via root `config.py` (T-ENV-1 resolved I-1).

---

### 2.2 Table Schemas (inferred from INSERT statements)

#### `market_data` (MySQL — `investments`)
```sql
CREATE TABLE market_data (
    ticker      VARCHAR(20),
    timestamp   DATETIME,
    last_price  DECIMAL(18,6),
    volume      BIGINT,
    PRIMARY KEY (ticker, timestamp)  -- INSERT IGNORE implies unique key
);
```
Populated by: `yfinance_websocket/websocket_server.py`, `populate_intraday.py`, `api/websocket_db_insert.py`

---

#### `ticks` (PostgreSQL — `marketdata`)
```sql
CREATE TABLE ticks (
    time         TIMESTAMPTZ,
    instrument   VARCHAR(50),
    bid_volume   BIGINT,
    bid_price    NUMERIC,
    ask_price    NUMERIC,
    ask_volume   BIGINT,
    last_price   NUMERIC,
    total_volume BIGINT,
    low          NUMERIC,
    high         NUMERIC,
    prev_close   NUMERIC
);
```
Populated by: `job/futuros_tick_by_tick.py`, `web_scraping/matriz/matrizwb.py`

---

#### `orders` (PostgreSQL — `marketdata`)
```sql
CREATE TABLE orders (
    instrument  VARCHAR(50),
    time        TIMESTAMPTZ,
    price       NUMERIC,
    volume      BIGINT,
    side        CHAR(1),   -- 'B' (buy) or 'S' (sell)
    UNIQUE (instrument, time, price, volume, side)  -- ON CONFLICT DO NOTHING
);
```
Populated by: `job/order_side.py`, `web_scraping/matriz/order_side.py`

---

#### `cookies` (PostgreSQL — `marketdata`)
```sql
CREATE TABLE cookies (
    time   TIMESTAMPTZ,
    name   VARCHAR(100),
    value  TEXT
);
```
Populated by: `job/get_cookies.py`, `web_scraping/matriz/get_cookies.py`

---

#### `binance_ticks` (PostgreSQL — `marketdata`)
```sql
CREATE TABLE binance_ticks (
    symbol     VARCHAR(20),
    timestamp  TIMESTAMPTZ,
    open       NUMERIC,
    high       NUMERIC,
    low        NUMERIC,
    close      NUMERIC,
    volume     NUMERIC,
    UNIQUE (symbol, timestamp)
);
```
Populated by: `monitor/data_stream.py`

---

### 2.3 Key Wire Formats

#### MAE REST response (P1) — example fields used downstream
```json
{
  "ticker": "USMEP",
  "segmento": "Minorista",
  "minimo": 1234.5,
  "maximo": 1250.0,
  "ultimo": 1245.0,
  "variacion": 0.012,
  "descripcion": "...",
  "ultimaTasa": 45.5,
  "volumen": 1000000
}
```

#### Matriz WebSocket tick message (P2) — pipe-delimited
```
M:<instrument>|<internal_id>|<seq_or_phase>|<bid_price>|<ask_price>|<bid_size>|<last_price>|<timestamp>|<turnover>|<ask_size>|<open>|<high>|<low>|<reserved2>|<prev_close>|<prev_date>|r1|r2|r3|<settlement_price>|<settlement_date>
```

#### MatbaRofex Primary WS tick message (P3) — pipe-delimited, prefixed `M:`
Fields: `instrument, sequence, bid_qty, last_price, ask_price, volume, prev_close, timestamp, trades, turnover, turnover_clean, open, high, low, open_interest, settlement_price, settlement_date, previous_settlement_price, previous_settlement_date, reference_price, reference_date`

#### yfinance OHLCV row (P6)
```json
{ "Open": 1.23, "High": 1.25, "Low": 1.20, "Close": 1.22, "Adj Close": 1.22, "Volume": 100000 }
```

#### Binance kline (P7)
```json
{ "timestamp": "<ms epoch>", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 500.0 }
```

---

## 3. Environment & Dependencies

### 3.1 Python Version
- Runtime: CPython 3.10.12 (system python, `.venv` at `programming/.venv`).
- Original scripts used 3.8 (broken symlink — resolved, I-10 fix).

### 3.2 Key Dependencies
```
aiohttp
httpx
requests
websocket-client
websockets
yfinance
pandas
psycopg2-binary
mysql-connector-python
playwright
binance-connector
tabulate
humanize
rich
pytz
python-dotenv
pydantic
```

### 3.3 Execution Model (current)
- Long-running processes managed by systemd (`wsclient.service`, `binance_monitor.service`).
- Polling loop: `job/order_side.py` via crontab every 2 min during market hours.
- Trading-hours guard: 10:00–17:00 ART / 09:30–16:00 ET.
- DB connections via `shared/db_pool.py` (`ThreadedConnectionPool`, auto-reconnects).

### 3.4 Auth / Secrets
All credentials loaded from `.env` via root `config.py` (T-ENV-1 complete).

| Secret | Location |
|--------|----------|
| MySQL password | `.env` → `MYSQL_PASSWORD` |
| PostgreSQL password | `.env` → `PG_PASSWORD` |
| Binance API Key + Secret | `.env` → `BINANCE_API_KEY`, `BINANCE_SECRET_KEY` |
| Matriz login credentials | `.env` → `MATRIZ_USER`, `MATRIZ_PASS` |
| Email SMTP password | `.env` → `EMAIL_PASSWORD` |

---

## 4. Known Issues (pre-SDD audit — all resolved)

| ID | File | Issue | Resolution |
|----|------|-------|------------|
| I-1 | `web_scraping/matriz/config.py` vs `job/config.py` | DB host mismatch (`192.168.0.244` vs `localhost`) | T-ENV-1: unified to `localhost` via root `config.py` |
| I-2 | `job/futuros_tick_by_tick.py`, `web_scraping/matriz/matrizwb.py` | WebSocket URL contains hardcoded session tokens (expire) | Tokens refreshed via cookie rotation |
| I-3 | All scrapers | No structured logging — only `print()` statements | T-LOG-1: `logger.py` module |
| I-4 | All scrapers | No error notification to architect on platform structure change | T-ERR-1: `notifier.py` |
| I-5 | `web_scraping/matriz/order_side.py` | `orders` INSERT missing `instrument` column | T-DB-6: `instrument` added to INSERT |
| I-6 | All config files | Credentials in plaintext source files | T-ENV-1: `.env` + `python-dotenv` |
| I-7 | `web_scraping/A3/stock_extracting.py` | Scrapes Yahoo Finance HTML (fragile) | Replaced by yfinance lib (P6) |
| I-8 | Multiple modules | Duplicate `get_cookies.py` in `job/` and `web_scraping/matriz/` | T-COOKIE-1: `shared/get_cookies.py` |
| I-9 | Multiple modules | DB connection opened per-message (no pooling) | T-DB-1/T-DB-2: `shared/db_pool.py` |

---

## 5. SDD Task List

See `TASKS.md`.

---

## 6. Infrastructure & Persistence

> Audited: 2026-03-14. Updated: 2026-03-20. Source: live `systemctl`, `crontab -l`, `pg_lsclusters`, `psql \d`.

### 6.1 Execution Infrastructure

#### Systemd Services

| Unit | Description | Script | State | Restart |
|------|-------------|--------|-------|---------|
| `wsclient.service` | Matriz WebSocket tick ingestor | `job/futuros_tick_by_tick.py` | **active** (triggered by timer) | `on-failure` |
| `binance_monitor.service` | Binance kline ingestor | `monitor/main.py` | **active (running)** | `on-failure` |

#### Systemd Timers

| Unit | Schedule | Triggers | State |
|------|----------|----------|-------|
| `wsclient.timer` | `Mon–Fri 10:00 ART` | `wsclient.service` | **active (waiting)** |
| `wsclient-stop.timer` | `Mon–Fri 17:00 ART` | `wsclient-stop.service` | **active (waiting)** |
| `binance_monitor.timer` | `Mon–Fri 10:00 ART` | `binance_monitor.service` | **active (waiting)** |

#### Crontab (`julian`)

| Schedule | Command | Purpose |
|----------|---------|---------|
| `*/2 10-16 Mon–Fri` | `.venv/bin/python job/order_side.py` | Poll Matriz REST trades every 2 min during market hours |

> `CRON_TZ=America/Argentina/Buenos_Aires` is set in crontab.
> Debug `date >>` entry removed (I-12). Old `systemctl stop` entry replaced by `wsclient-stop.timer` (I-11).
> Crontab venv path fixed from broken `python3.8` symlink to `.venv/bin/python`.

---

### 6.2 Database Infrastructure

#### PostgreSQL Clusters

| Version | Cluster | Port | Status | Data Directory |
|---------|---------|------|--------|----------------|
| 12 | main | **5432** | online | `/var/lib/postgresql/12/main` |
| 14 | main | **5433** | online | `/var/lib/postgresql/14/main` |

> All project databases live on PG 12 (port 5432). PG 14 is unused by this project.

#### PostgreSQL Databases (port 5432)

| Database | Owner | Purpose |
|----------|-------|---------|
| `marketdata` | postgres | Primary time-series store — all scraper output |
| `mercadoLibre` | postgres | MercadoLibre product/price scraper (separate project) |
| `servermonitor` | postgres | Server health monitoring |

#### MySQL

| Database | User | Purpose |
|----------|------|---------|
| `investments` | `black` | yfinance OHLCV data (`market_data`, `ADR_RATIO`, `cryptocurrency_data`) |

---

### 6.3 Actual Table Schemas (`marketdata` — PostgreSQL 12)

> `ticks`, `orders`, and `binance_ticks` are **TimescaleDB hypertables** (v2.11.2 community), compression enabled.

#### `ticks` — TimescaleDB hypertable
| Column | Type | Nullable |
|--------|------|----------|
| time | `TIMESTAMPTZ` NOT NULL | DEFAULT `now()` |
| instrument | `TEXT` NOT NULL | |
| bid_volume | `BIGINT` NOT NULL | |
| bid_price | `NUMERIC(18,6)` NOT NULL | |
| ask_price | `NUMERIC(18,6)` NOT NULL | |
| ask_volume | `BIGINT` NOT NULL | |
| last_price | `NUMERIC(18,6)` NOT NULL | |
| total_volume | `BIGINT` NOT NULL | |
| low | `NUMERIC(18,6)` NOT NULL | |
| high | `NUMERIC(18,6)` NOT NULL | |
| prev_close | `NUMERIC(18,6)` NOT NULL | |

Chunk interval: **1 day** (new chunks), 7 days (legacy). Compression: **enabled** (`segment by instrument, order by time DESC`). Policy: compress chunks > 7 days old.
Historical `high`/`low` backfilled 2026-03-20 — 11.3M rows corrected (I-20).

#### `orders` — TimescaleDB hypertable
| Column | Type | Nullable |
|--------|------|----------|
| time | `TIMESTAMPTZ` NOT NULL | |
| price | `NUMERIC(18,6)` NOT NULL | |
| volume | `BIGINT` NOT NULL | |
| side | `CHAR(1)` NOT NULL | |
| instrument | `VARCHAR(50)` NOT NULL | ✅ fixed I-13 |

Compression: **enabled**. Policy: compress chunks > 7 days old.

#### `cookies`
| Column | Type |
|--------|------|
| name | `VARCHAR(50)` NOT NULL |
| value | `VARCHAR(1000)` NOT NULL |
| time | `TIMESTAMPTZ` NOT NULL | ✅ fixed I-14 |

#### `binance_ticks` — TimescaleDB hypertable
| Column | Type |
|--------|------|
| symbol | `VARCHAR(20)` NOT NULL |
| timestamp | `TIMESTAMPTZ` NOT NULL | ✅ fixed I-14 |
| open/high/low/close/volume | `NUMERIC(18,6)` | ✅ fixed I-15 |

3 chunks. ✅ fixed I-16.

#### Decision-Making Tables (populated by second repository)
| Table | Purpose |
|-------|---------|
| `backtest_runs` | Strategy backtest results (return, drawdown, win rate, Sharpe) |
| `trade_metrics` | Per-run avg win/loss, Sharpe, Sortino |
| `signal_stats` | Signal name → count per run |
| `signal_reasons` | Signal trigger reasons |
| `market_observations` | Live bid/ask/spread snapshots per run |
| `positions` | Open positions per run |
| `trade_snapshots` | Individual trade records |

---

### 6.4 Connection Limits & Current Load

| Parameter | Value |
|-----------|-------|
| `max_connections` (PG 12) | **100** ✅ raised from 50 (I-17) |
| Connection strategy | `shared/db_pool.py` — `ThreadedConnectionPool(minconn=1, maxconn=5)`, auto-reconnects on PG restart |

---

### 6.5 Infrastructure Issues (all resolved)

| ID | Component | Issue | Resolution |
|----|-----------|-------|------------|
| I-10 | `binance_monitor.service` | No timer/crontab — never auto-started | `binance_monitor.timer` added (T-INFRA-2) |
| I-11 | `wsclient.timer` | Stop relied on fragile crontab `systemctl stop` | `wsclient-stop.timer` added (T-INFRA-3) |
| I-12 | `crontab` | Debug `date >>` entry ran every minute | Removed (T-INFRA-4) |
| I-13 | `orders.instrument` | Column was nullable; older scraper omitted it | `NOT NULL` set, INSERT fixed (T-DB-6) |
| I-14 | `cookies.time`, `binance_ticks.timestamp` | `TIMESTAMP` without timezone | Converted to `TIMESTAMPTZ` (T-DB-5) |
| I-15 | `binance_ticks` | `DOUBLE PRECISION` for price/volume | Converted to `NUMERIC(18,6)` (T-DB-4) |
| I-16 | `binance_ticks` | Not a TimescaleDB hypertable | `create_hypertable()` applied (T-DB-4) |
| I-17 | PostgreSQL | `max_connections=50` with per-message connections | Raised to 100; pool added (T-DB-2) |
| I-18 | PostgreSQL | Compression disabled on `ticks`/`orders` | Enabled + 53 chunks compressed (T-DB-3) |
| I-19 | `wsclient.service` | No `[Install]` section — unit was `static` | `[Install]` added, `systemctl enable`d (T-INFRA-1) |
| I-20 | `job/futuros_tick_by_tick.py` | `high`/`low` fields swapped in parser | Fixed + 11.3M rows backfilled (T-DB-8) |
