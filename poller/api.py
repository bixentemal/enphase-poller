import logging

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from psycopg2.extras import RealDictCursor

from poller import storage
from poller.config import API_KEY

log = logging.getLogger(__name__)

app = FastAPI(title="Enphase Poller API")

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


@app.get("/api/live", dependencies=[Depends(_check_api_key)])
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


@app.get("/api/today", dependencies=[Depends(_check_api_key)])
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


@app.get("/api/week", dependencies=[Depends(_check_api_key)])
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


@app.get("/api/health", dependencies=[Depends(_check_api_key)])
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
    # Serialize timestamps
    for r in recent:
        r["ts"] = str(r["ts"])
    return {
        "event_summary": [dict(r) for r in events],
        "recent_events": [dict(r) for r in recent],
    }


@app.get("/api/summary", dependencies=[Depends(_check_api_key)])
def summary():
    return {
        "live": live(),
        "today": today(),
        "week": week(),
        "health": health(),
    }
