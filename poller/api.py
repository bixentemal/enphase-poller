import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from psycopg2.extras import RealDictCursor

from poller import storage
from poller.config import API_KEY

log = logging.getLogger(__name__)

app = FastAPI(
    title="Enphase Poller API",
    description="REST API for querying solar PV metrics from an Enphase Envoy system. "
    "Provides live readings, daily/weekly summaries, flexible energy queries, and poller health status.",
    version="1.0.0",
)

_api_key_header = APIKeyHeader(name="X-API-Key")


def _check_api_key(key: str = Security(_api_key_header)):
    if not API_KEY or key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _query(sql, params=None):
    conn = storage.get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def _query_one(sql, params=None):
    rows = _query(sql, params)
    return rows[0] if rows else None


@app.get(
    "/api/live",
    dependencies=[Depends(_check_api_key)],
    summary="Current power readings",
    description="Returns the latest instantaneous power values: solar production (W), "
    "house consumption (W), grid import/export (W), and active inverter count.",
    tags=["Live"],
    responses={200: {"content": {"application/json": {"example": {
        "production_w": 6820.5,
        "active_inverters": 18,
        "consumption_w": 1450.3,
        "grid_w": -5370.2,
        "timestamp": "2026-04-14 14:30:00+00:00",
    }}}}},
)
def live():
    rows = _query("""
        SELECT DISTINCT ON (source_type)
            source_type, w_now, active_count,
            source_reading_time
        FROM production_overview
        WHERE source_type IN ('production', 'total-consumption', 'net-consumption')
        ORDER BY source_type, source_reading_time DESC
    """)
    result = {}
    for r in rows:
        st = r["source_type"]
        if st == "production":
            result["production_w"] = r["w_now"]
            result["active_inverters"] = r["active_count"]
        elif st == "total-consumption":
            result["consumption_w"] = r["w_now"]
        elif st == "net-consumption":
            result["grid_w"] = r["w_now"]
    result["timestamp"] = str(rows[0]["source_reading_time"]) if rows else None
    return result


@app.get(
    "/api/today",
    dependencies=[Depends(_check_api_key)],
    summary="Today's energy totals",
    description="Returns today's cumulative energy: production (kWh), consumption (kWh), "
    "self-consumption percentage, grid export (kWh), and grid import (kWh). "
    "Computed from meter reading deltas since midnight.",
    tags=["Daily"],
    responses={200: {"content": {"application/json": {"example": {
        "production_kwh": 35.2,
        "consumption_kwh": 12.8,
        "self_consumption_pct": 63.6,
        "grid_export_kwh": 22.4,
        "grid_import_kwh": 3.1,
    }}}}},
)
def today():
    prod = _query_one("""
        SELECT ROUND(((MAX(act_energy_delivered) - MIN(act_energy_delivered)) / 1000.0)::numeric, 2) AS kwh
        FROM meter_readings
        WHERE meter_type = 'production'
          AND source_reading_time >= date_trunc('day', NOW())
    """)
    cons = _query_one("""
        SELECT ROUND(((MAX(act_energy_delivered) - MIN(act_energy_delivered)) / 1000.0)::numeric, 2) AS kwh
        FROM meter_readings
        WHERE meter_type = 'net-consumption'
          AND source_reading_time >= date_trunc('day', NOW())
    """)
    prod_kwh = float(prod["kwh"]) if prod and prod["kwh"] else 0
    cons_kwh = float(cons["kwh"]) if cons and cons["kwh"] else 0
    self_consumption = round((1 - cons_kwh / prod_kwh) * 100, 1) if prod_kwh > 0 else 0

    grid_export = _query_one("""
        SELECT ROUND(((MAX(act_energy_received) - MIN(act_energy_received)) / 1000.0)::numeric, 2) AS kwh
        FROM meter_readings
        WHERE meter_type = 'net-consumption'
          AND source_reading_time >= date_trunc('day', NOW())
    """)
    grid_import = _query_one("""
        SELECT ROUND(((MAX(act_energy_delivered) - MIN(act_energy_delivered)) / 1000.0)::numeric, 2) AS kwh
        FROM meter_readings
        WHERE meter_type = 'net-consumption'
          AND source_reading_time >= date_trunc('day', NOW())
    """)

    return {
        "production_kwh": prod_kwh,
        "consumption_kwh": cons_kwh,
        "self_consumption_pct": self_consumption,
        "grid_export_kwh": float(grid_export["kwh"]) if grid_export and grid_export["kwh"] else 0,
        "grid_import_kwh": float(grid_import["kwh"]) if grid_import and grid_import["kwh"] else 0,
    }


@app.get(
    "/api/week",
    dependencies=[Depends(_check_api_key)],
    summary="Last 7 days daily breakdown",
    description="Returns daily production and consumption (kWh) for each of the last 7 days.",
    tags=["Daily"],
    responses={200: {"content": {"application/json": {"example": [
        {"day": "2026-04-08", "production_kwh": 32.1, "consumption_kwh": 18.5},
        {"day": "2026-04-09", "production_kwh": 28.7, "consumption_kwh": 15.2},
        {"day": "2026-04-10", "production_kwh": 35.4, "consumption_kwh": 20.1},
    ]}}}},
)
def week():
    rows = _query("""
        SELECT date_trunc('day', source_reading_time)::date AS day,
            ROUND(((MAX(act_energy_delivered) - MIN(act_energy_delivered)) / 1000.0)::numeric, 2) AS production_kwh
        FROM meter_readings
        WHERE meter_type = 'production'
          AND source_reading_time >= NOW() - INTERVAL '7 days'
        GROUP BY 1
        ORDER BY 1
    """)
    cons_rows = _query("""
        SELECT date_trunc('day', source_reading_time)::date AS day,
            ROUND(((MAX(act_energy_delivered) - MIN(act_energy_delivered)) / 1000.0)::numeric, 2) AS consumption_kwh
        FROM meter_readings
        WHERE meter_type = 'net-consumption'
          AND source_reading_time >= NOW() - INTERVAL '7 days'
        GROUP BY 1
        ORDER BY 1
    """)
    cons_by_day = {str(r["day"]): float(r["consumption_kwh"]) for r in cons_rows}
    result = []
    for r in rows:
        day = str(r["day"])
        prod = float(r["production_kwh"])
        cons = cons_by_day.get(day, 0)
        result.append({
            "day": day,
            "production_kwh": prod,
            "consumption_kwh": cons,
        })
    return result


@app.get(
    "/api/health",
    dependencies=[Depends(_check_api_key)],
    summary="Poller health status",
    description="Returns poller operational events from the last 24 hours: "
    "event type summary with counts, and the 10 most recent events with details. "
    "Event types include: startup, shutdown, error, gap_start, gap_end.",
    tags=["Health"],
    responses={200: {"content": {"application/json": {"example": {
        "event_summary": [
            {"event_type": "error", "severity": "error", "count": 3},
            {"event_type": "startup", "severity": "info", "count": 1},
        ],
        "recent_events": [
            {"ts": "2026-04-14 12:05:00+00:00", "event_type": "error", "severity": "error", "endpoint": "/ivp/meters/reports", "details": "Connection timeout"},
            {"ts": "2026-04-14 08:00:00+00:00", "event_type": "startup", "severity": "info", "endpoint": None, "details": "Poller started"},
        ],
    }}}}},
)
def health():
    events = _query("""
        SELECT event_type, severity, COUNT(*) AS count
        FROM poller_events
        WHERE ts >= NOW() - INTERVAL '24 hours'
        GROUP BY 1, 2
        ORDER BY count DESC
    """)
    recent = _query("""
        SELECT ts, event_type, severity, endpoint, details
        FROM poller_events
        WHERE ts >= NOW() - INTERVAL '24 hours'
        ORDER BY ts DESC
        LIMIT 10
    """)
    for r in recent:
        r["ts"] = str(r["ts"])
    return {
        "event_summary": [dict(r) for r in events],
        "recent_events": [dict(r) for r in recent],
    }


@app.get(
    "/api/summary",
    dependencies=[Depends(_check_api_key)],
    summary="Full system summary",
    description="Combines live readings, today's totals, weekly breakdown, and health status in a single response.",
    tags=["Live"],
)
def summary():
    return {
        "live": live(),
        "today": today(),
        "week": week(),
        "health": health(),
    }


_METRIC_CONFIG = {
    "production": {"meter_type": "production", "column": "act_energy_delivered"},
    "consumption": {"meter_type": "net-consumption", "column": "act_energy_delivered"},
    "grid_export": {"meter_type": "net-consumption", "column": "act_energy_received"},
    "grid_import": {"meter_type": "net-consumption", "column": "act_energy_delivered"},
}
_ALLOWED_GROUP_BY = {"hour", "day", "month"}
_ALLOWED_ORDER_BY = {"time", "value"}
_ALLOWED_ORDER = {"asc", "desc"}


@app.get(
    "/api/energy",
    dependencies=[Depends(_check_api_key)],
    summary="Flexible energy query",
    description="Query historical energy data with flexible filtering and aggregation. "
    "Use this endpoint to answer questions like:\n\n"
    "- **Day with max production this year**: `?metric=production&from=2026-01-01&order_by=value&order=desc&limit=1`\n"
    "- **Last week consumption day by day**: `?metric=consumption&from=2026-04-07&group_by=day`\n"
    "- **Hourly production yesterday**: `?metric=production&from=2026-04-13&to=2026-04-14&group_by=hour`\n"
    "- **Monthly grid export totals**: `?metric=grid_export&group_by=month`\n"
    "- **Top 5 consumption days**: `?metric=consumption&order_by=value&order=desc&limit=5`\n\n"
    "Returns energy in kWh, computed from cumulative meter counter deltas per time bucket.",
    tags=["Energy"],
    responses={200: {"content": {"application/json": {"example": {
        "metric": "production",
        "group_by": "day",
        "from": "2026-04-07",
        "to": "2026-04-15",
        "data": [
            {"time": "2026-04-07 00:00:00+00:00", "kwh": 32.1},
            {"time": "2026-04-08 00:00:00+00:00", "kwh": 28.7},
            {"time": "2026-04-09 00:00:00+00:00", "kwh": 35.4},
            {"time": "2026-04-10 00:00:00+00:00", "kwh": 18.2},
            {"time": "2026-04-11 00:00:00+00:00", "kwh": 40.1},
        ],
    }}}}},
)
def energy(
    metric: str = Query("production", description="Energy metric to query: production, consumption, grid_export, grid_import"),
    group_by: str = Query("day", description="Time bucket for aggregation: hour, day, month"),
    date_from: Optional[date] = Query(None, alias="from", description="Start date inclusive (ISO format, e.g. 2026-01-01). Defaults to 30 days ago."),
    date_to: Optional[date] = Query(None, alias="to", description="End date exclusive (ISO format). Defaults to tomorrow."),
    order_by: str = Query("time", description="Sort results by: time or value"),
    order: str = Query("asc", description="Sort direction: asc or desc"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Max number of rows to return"),
):
    if metric not in _METRIC_CONFIG:
        raise HTTPException(400, f"metric must be one of: {', '.join(_METRIC_CONFIG)}")
    if group_by not in _ALLOWED_GROUP_BY:
        raise HTTPException(400, f"group_by must be one of: {', '.join(_ALLOWED_GROUP_BY)}")
    if order_by not in _ALLOWED_ORDER_BY:
        raise HTTPException(400, f"order_by must be one of: {', '.join(_ALLOWED_ORDER_BY)}")
    if order not in _ALLOWED_ORDER:
        raise HTTPException(400, f"order must be one of: {', '.join(_ALLOWED_ORDER)}")

    cfg = _METRIC_CONFIG[metric]
    if date_from is None:
        date_from = date.today() - timedelta(days=30)
    if date_to is None:
        date_to = date.today() + timedelta(days=1)

    col = cfg["column"]
    order_col = "time" if order_by == "time" else "kwh"

    sql = f"""
        SELECT date_trunc('{group_by}', source_reading_time) AS time,
            ROUND(((MAX({col}) - MIN({col})) / 1000.0)::numeric, 2) AS kwh
        FROM meter_readings
        WHERE meter_type = %s
          AND source_reading_time >= %s
          AND source_reading_time < %s
        GROUP BY 1
        ORDER BY {order_col} {order}
    """
    params = [cfg["meter_type"], date_from, date_to]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    rows = _query(sql, params)
    return {
        "metric": metric,
        "group_by": group_by,
        "from": str(date_from),
        "to": str(date_to),
        "data": [{"time": str(r["time"]), "kwh": float(r["kwh"])} for r in rows],
    }
