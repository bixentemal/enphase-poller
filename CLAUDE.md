# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python 3.12 application that polls solar energy data from a local Enphase Envoy (IQ Gateway) at multiple cadences, stores time-series metrics in PostgreSQL 16, and serves them via a FastAPI REST API.

## Commands

```bash
# Run locally
pip install -r requirements.txt
python -m poller.main

# Run with Docker Compose (includes PostgreSQL)
cp .env.example .env   # edit with your token/IP
docker compose up --build -d

# Rebuild after code changes
docker compose up --build -d poller
```

No test suite or linter is configured.

## Architecture

### Threading Model

`poller/main.py:main()` starts two threads:
1. **Polling thread** (daemon) — single DB connection, 1-second tick loop with 4 independent timers
2. **API thread** (main) — Uvicorn/FastAPI on port 8000, opens a fresh DB connection per request

### Polling Cadences

| Endpoint | Interval | Table | Purpose |
|----------|----------|-------|---------|
| `/production.json` | 30s | `production_overview` | Instantaneous watts per source type |
| `/ivp/meters/readings` | 30s | `meter_readings` (+`meter_reading_channels`) | Power, voltage, cumulative energy per meter |
| `/ivp/meters/reports` | 60s | `meter_reports` | Cumulative Wh counters (gap tracking source) |
| `/api/v1/production/inverters` | 300s | `inverter_readings` | Per-inverter watt output |

### Gap Tracking

`GapTracker` in `main.py` only applies to `/ivp/meters/reports` (the only endpoint with monotonic cumulative counters). On recovery, it estimates missed energy from counter deltas and writes `gap_start`/`gap_end` events to `poller_events`.

### Data Deduplication

All insert functions use `ON CONFLICT DO NOTHING` with UNIQUE constraints on `(source_reading_time, device_id)`. The helper `_ts_or_fallback()` in `storage.py` handles `readingTime=0` from the Envoy by snapping `collected_at` to the nearest poll interval boundary.

### REST API

Six endpoints under `/api/` — all require `X-API-Key` header. Swagger docs at `/docs`.

Energy queries (`/api/today`, `/api/week`, `/api/energy`) compute kWh from `MAX - MIN` of cumulative `act_energy_delivered`/`act_energy_received` counters in `meter_readings`, grouped by time bucket.

## Key Environment Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `ENPHASE_TOKEN` | Yes | — | JWT from entrez.enphaseenergy.com (see `how_to_create_token.md`) |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `ENVOY_HOST` | No | `envoy.local` | Envoy IP or hostname |
| `API_KEY` | No | — | If set, required for all API requests |
| `ENABLE_CHANNEL_READINGS` | No | `false` | Per-phase data; adds ~19M rows/year |

## Database

Schema auto-bootstraps on startup via `storage.bootstrap_schema()` reading `schema.sql`. No migration system — all DDL is idempotent (`CREATE TABLE IF NOT EXISTS`).

## Conventions

- Grafana dashboards must use modern panel types (not deprecated ones), object-style datasource references, and `::numeric` cast before `ROUND()`.
- Prefer polling over SSE and typed tables over JSONB.
