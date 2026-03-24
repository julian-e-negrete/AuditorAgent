# TASKS.md — SDD Task List
> Each task references a requirement in SPEC.md.
> Execute one block at a time. Run tests after each. Await architect confirmation before proceeding.

---

## Phase 1 — Foundation

- [x] **T-ENV-1** · Externalize all secrets to `.env` + `python-dotenv`
  - Ref: SPEC §3.4, §4 I-6
  - Replace all `config.py` credential files with a single `.env` at repo root.
  - Unify DB host discrepancy (SPEC §4 I-1).

- [x] **T-LOG-1** · Implement structured logger (`logging` stdlib, JSON formatter)
  - Ref: SPEC §4 I-3
  - Single `logger.py` module imported by all scrapers.
  - Log level configurable via `LOG_LEVEL` env var.

---

## Phase 2 — Observability

- [x] **T-OBS-1** · Add I/O logging to every HTTP fetch (headers + body)
  - Ref: SPEC §2.3, Phase 2 requirement "Refactor for Observability"
  - Wrap `aiohttp`, `httpx`, `requests` calls in a `fetch_with_log()` helper.
  - Log: request URL, method, request headers, response status, response body (truncated to 4 KB).

- [x] **T-OBS-2** · Add I/O logging to every WebSocket message
  - Ref: SPEC §2.3
  - Log raw inbound message before parsing, with timestamp and source platform ID.

---

## Phase 3 — Reliability

- [x] **T-ERR-1** · Standardize error handling — fail-fast with architect notification
  - Ref: SPEC §4 I-4, Phase 2 requirement "Standardize Error Handling"
  - Create `notifier.py`: sends email (reuse SMTP config from `monitor/config.py`) on unhandled exception or schema mismatch.
  - Each scraper wraps its main loop in a `try/except` that calls `notifier.notify(platform_id, error)`.

- [x] **T-ERR-2** · Schema validation on every parsed payload
  - Ref: SPEC §2.2, §2.3
  - Use `pydantic` models matching the data contracts in SPEC §2.2.
  - On validation failure: log the raw payload, call `notifier.notify()`, and skip the record (do not crash the stream).

- [x] **T-COOKIE-1** · Deduplicate `get_cookies.py`
  - Ref: SPEC §4 I-8
  - Single canonical `shared/get_cookies.py`; remove duplicates in `job/` and `web_scraping/matriz/`.

- [x] **T-DB-1** · Replace per-message DB connections with a connection pool
  - Ref: SPEC §4 I-9
  - Use `psycopg2.pool.ThreadedConnectionPool` for PostgreSQL.
  - Single pool instance per process, acquired/released per operation.

---

## Phase 4 — Modularization

- [x] **T-MOD-1** · Isolate each scraper into its own module under `scrapers/`
  - Ref: SPEC §1, Phase 2 requirement "Modularize Fetchers"
  - Structure:
    ```
    scrapers/
      mae/        # P1
      matriz/     # P2
      primary/    # P3
      byma/       # P4
      nasdaq/     # P5
      yfinance/   # P6
      binance/    # P7
    shared/
      logger.py
      notifier.py
      db_pool.py
      get_cookies.py
      models.py   # pydantic schemas
    ```
  - Each scraper module exposes a single `run()` coroutine.
  - No cross-module imports except from `shared/`.

---

## Phase 5 — Testing

- [x] **T-TEST-1** · Unit tests for pydantic schema validation (SPEC §2.2)
  - Ref: SPEC §2.2, Phase 2 requirement "Unit Testing"
  - Test valid payloads pass, invalid payloads raise `ValidationError`.
  - One test file per platform: `tests/test_schema_<platform>.py`.

- [x] **T-TEST-2** · Unit tests for message parsers
  - Ref: SPEC §2.3
  - Test `parse_market_message()` (Matriz/Primary pipe format) with fixture strings.
  - Test edge cases: field count mismatch, non-numeric values.

- [x] **T-TEST-3** · Integration smoke test for each fetcher
  - Ref: SPEC §1
  - Mock HTTP/WS responses; assert DB insert is called with correct arguments.

---

## Execution Rules

1. Tasks are executed **in order**, one at a time.
2. After each task: run `pytest` and report results.
3. Do not start the next task without architect confirmation.
4. All generated code must include a comment referencing the SPEC.md section it implements.
   Example: `# SPEC §3.4 T-ENV-1 — load credentials from environment`

---

## Phase 6 — Infrastructure Health (from §6.5 audit)

- [x] **T-INFRA-1** · Fix `wsclient.service` unit — add `[Install]` section, enable it
  - Ref: SPEC §6.5 I-19
  - Add `WantedBy=timers.target` under `[Install]` so `systemctl enable` works.

- [x] **T-INFRA-2** · Add timer + auto-start for `binance_monitor.service`
- [x] **T-INFRA-3** · Replace fragile crontab stop with a systemd `OnCalendar` stop timer
- [x] **T-INFRA-4** · Remove debug crontab entry

---

## Phase 7 — Database Scalability & Correctness

- [x] **T-DB-2** · Implement connection pooling — replace per-message connections
  - Ref: SPEC §6.4, §6.5 I-17, Phase 3 T-DB-1
  - Use `psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=5)` in `shared/db_pool.py`.
  - All WebSocket `on_message` handlers acquire/release from pool instead of connect/close.
  - Raise `max_connections` to 100 in `postgresql.conf` (`/etc/postgresql/12/main/postgresql.conf`).

- [x] **T-DB-3** · Enable TimescaleDB compression on `ticks` and `orders`
  - Ref: SPEC §6.3, §6.5 I-18
  - `ALTER TABLE ticks SET (timescaledb.compress, timescaledb.compress_orderby='time DESC');`
  - `SELECT add_compression_policy('ticks', INTERVAL '7 days');`
  - Same for `orders`. Expected reduction: ~90% on older chunks.

- [x] **T-DB-4** · Convert `binance_ticks` to a TimescaleDB hypertable
  - Ref: SPEC §6.5 I-16
  - `SELECT create_hypertable('binance_ticks', 'timestamp', migrate_data => true);`
  - Change `timestamp` column to `TIMESTAMPTZ`.
  - Change `open/high/low/close/volume` from `DOUBLE PRECISION` to `NUMERIC(18,6)`.

- [x] **T-DB-5** · Fix timezone consistency — `cookies.time` and `binance_ticks.timestamp`
  - Ref: SPEC §6.5 I-14
  - `ALTER TABLE cookies ALTER COLUMN time TYPE TIMESTAMPTZ USING time AT TIME ZONE 'America/Argentina/Buenos_Aires';`
  - Same for `binance_ticks.timestamp`.

- [x] **T-DB-6** · Fix `orders.instrument` nullable constraint
  - Ref: SPEC §6.5 I-13
  - Backfill NULLs if any exist, then `ALTER TABLE orders ALTER COLUMN instrument SET NOT NULL;`
  - Fix `web_scraping/matriz/order_side.py` to always include `instrument` in INSERT.

- [x] **T-DB-7** · Tune TimescaleDB chunk interval for `ticks`
  - Ref: SPEC §6.3 (current: 168h/weekly chunks, ~100 MB each)
  - Evaluate reducing to `INTERVAL '1 day'` for faster chunk compression and drop policies.
  - `SELECT set_chunk_time_interval('ticks', INTERVAL '1 day');` (applies to new chunks only).

- [x] **T-DB-8** · Fix swapped `high`/`low` in Matriz parser and backfill historical data
  - Ref: SPEC §6.5 I-20
  - Fix `scrapers/matriz/run.py`: swap `low=fields[11]` → `high=fields[11]`, `high=fields[12]` → `low=fields[12]`.
  - Backfill: `UPDATE ticks SET high = low, low = high WHERE instrument IN (...) AND time < '<fix_deploy_time>';`
  - Update `tests/test_parser_matriz.py` assertions after fix.
