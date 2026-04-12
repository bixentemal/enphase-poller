# Enphase Poller

A simple Python poller that collects solar production, consumption, and power quality data from a local Enphase Envoy (IQ Gateway) and stores it in PostgreSQL for Grafana dashboards.

## Features

- Polls 4 Envoy local API endpoints at different cadences (15s to 5min)
- Stores full production, consumption, meter, and per-inverter data
- Deduplicates using Envoy-provided timestamps
- Detects polling gaps and estimates missed energy using cumulative counters
- Designed for long-term, consistent history

## Requirements

- Enphase Envoy IQ Gateway with firmware D7+ (JWT auth)
- PostgreSQL database
- Python 3.12+

## Quick Start

```bash
cp .env.example .env
# Edit .env with your token and database URL

pip install -r requirements.txt
python -m poller.main
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVOY_HOST` | `envoy.local` | Envoy hostname or IP |
| `ENPHASE_TOKEN` | (required) | JWT access token |
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `POLL_INTERVAL` | `30` | Seconds between production/meter polls |
| `METER_REPORT_POLL_INTERVAL` | `60` | Seconds between cumulative counter polls |
| `INVERTER_POLL_INTERVAL` | `300` | Seconds between per-inverter polls |
| `ENABLE_CHANNEL_READINGS` | `false` | Store per-phase meter channel data (~19M extra rows/year) |

## Getting a Token

See [how_to_create_token.md](how_to_create_token.md) for instructions on generating an Envoy access token.

## Docker

```bash
docker build -t enphase-poller .
docker run --env-file .env enphase-poller
```

## Database Schema

The schema is automatically created on startup. See [schema.sql](schema.sql) for the full definition.

### Tables

| Table | Source | Cadence |
|-------|--------|---------|
| `production_overview` | `/production.json` | 15s |
| `meter_readings` | `/ivp/meters/readings` | 15s |
| `meter_reading_channels` | `/ivp/meters/readings` (per-phase) | 15s |
| `meter_reports` | `/ivp/meters/reports` | 60s |
| `inverter_readings` | `/api/v1/production/inverters` | 300s |
| `poller_events` | internal | on error/gap |
