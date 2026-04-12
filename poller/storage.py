import logging
import os
from datetime import datetime, timezone

import psycopg2

from poller.config import DATABASE_URL, POLL_INTERVAL

log = logging.getLogger(__name__)


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def bootstrap_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    with open(schema_path) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    log.info("Schema bootstrapped")


def _ts(epoch):
    """Convert unix epoch to timezone-aware datetime."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _ts_or_fallback(epoch, collected_at):
    """Convert unix epoch to datetime. If epoch is 0/None, truncate collected_at
    to the poll interval boundary as a synthetic timestamp."""
    if epoch:
        return _ts(epoch)
    # Truncate to POLL_INTERVAL boundary
    ts_epoch = int(collected_at.timestamp())
    bucket = ts_epoch - (ts_epoch % POLL_INTERVAL)
    return datetime.fromtimestamp(bucket, tz=timezone.utc)


def _execute_batch(cur, sql, rows):
    """Execute inserts one by one and return the count of actually inserted rows
    (not skipped by ON CONFLICT DO NOTHING)."""
    inserted = 0
    for row in rows:
        cur.execute(sql, row)
        inserted += cur.rowcount
    return inserted


def insert_production_overview(conn, data, collected_at):
    rows = []
    for section_name, items in [("production", data.get("production", [])),
                                 ("consumption", data.get("consumption", [])),
                                 ("storage", data.get("storage", []))]:
        for item in items:
            reading_time = item.get("readingTime")
            source_type = item.get("measurementType") or item.get("type", section_name)
            rows.append((
                collected_at,
                _ts_or_fallback(reading_time, collected_at),
                source_type,
                item.get("activeCount"),
                item.get("wNow"),
                item.get("whLifetime"),
                item.get("whToday"),
                item.get("whLastSevenDays"),
                item.get("vahLifetime"),
                item.get("vahToday"),
                item.get("varhLeadLifetime"),
                item.get("varhLeadToday"),
                item.get("varhLagLifetime"),
                item.get("varhLagToday"),
                item.get("rmsCurrent"),
                item.get("rmsVoltage"),
                item.get("reactPwr"),
                item.get("apprntPwr"),
                item.get("pwrFactor"),
                item.get("whNow"),
                item.get("state"),
            ))

    if not rows:
        return 0

    sql = """
        INSERT INTO production_overview (
            collected_at, source_reading_time, source_type,
            active_count, w_now, wh_lifetime, wh_today, wh_last_seven_days,
            vah_lifetime, vah_today, varh_lead_lifetime, varh_lead_today,
            varh_lag_lifetime, varh_lag_today,
            rms_current, rms_voltage, reactive_power, apparent_power, power_factor,
            wh_now, state
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        ) ON CONFLICT DO NOTHING
    """
    with conn.cursor() as cur:
        inserted = _execute_batch(cur, sql, rows)
    conn.commit()
    return inserted


def insert_meter_readings(conn, data, meter_types, collected_at, enable_channels=False):
    reading_rows = []
    channel_rows = []

    for meter in data:
        reading_time = meter.get("timestamp")
        if not reading_time:
            continue
        ts = _ts(reading_time)
        eid = meter["eid"]
        meter_type = meter_types.get(eid, "unknown")

        reading_rows.append((
            collected_at, ts, eid, meter_type,
            meter.get("activePower"),
            meter.get("apparentPower"),
            meter.get("reactivePower"),
            meter.get("voltage"),
            meter.get("current"),
            meter.get("freq"),
            meter.get("pwrFactor"),
            meter.get("actEnergyDlvd"),
            meter.get("actEnergyRcvd"),
            meter.get("apparentEnergy"),
            meter.get("reactEnergyLagg"),
            meter.get("reactEnergyLead"),
        ))

        if enable_channels:
            for ch in meter.get("channels", []):
                ch_ts = ch.get("timestamp")
                if not ch_ts:
                    continue
                channel_rows.append((
                    collected_at, _ts(ch_ts), eid, ch["eid"],
                    ch.get("activePower"),
                    ch.get("apparentPower"),
                    ch.get("reactivePower"),
                    ch.get("voltage"),
                    ch.get("current"),
                    ch.get("freq"),
                    ch.get("pwrFactor"),
                    ch.get("actEnergyDlvd"),
                    ch.get("actEnergyRcvd"),
                    ch.get("apparentEnergy"),
                    ch.get("reactEnergyLagg"),
                    ch.get("reactEnergyLead"),
                ))

    meter_sql = """
        INSERT INTO meter_readings (
            collected_at, source_reading_time, meter_eid, meter_type,
            active_power, apparent_power, reactive_power,
            voltage, current_a, frequency, power_factor,
            act_energy_delivered, act_energy_received,
            apparent_energy, reactive_energy_lag, reactive_energy_lead
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """
    channel_sql = """
        INSERT INTO meter_reading_channels (
            collected_at, source_reading_time, meter_eid, channel_eid,
            active_power, apparent_power, reactive_power,
            voltage, current_a, frequency, power_factor,
            act_energy_delivered, act_energy_received,
            apparent_energy, reactive_energy_lag, reactive_energy_lead
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """
    mr_inserted = 0
    mc_inserted = 0
    with conn.cursor() as cur:
        if reading_rows:
            mr_inserted = _execute_batch(cur, meter_sql, reading_rows)
        if channel_rows:
            mc_inserted = _execute_batch(cur, channel_sql, channel_rows)
    conn.commit()
    return mr_inserted, mc_inserted


def insert_meter_reports(conn, data, collected_at):
    rows = []
    for report in data:
        reading_time = report.get("createdAt")
        if not reading_time:
            continue
        cumulative = report.get("cumulative", {})
        rows.append((
            collected_at,
            _ts(reading_time),
            report["reportType"],
            cumulative.get("currW"),
            cumulative.get("actPower"),
            cumulative.get("apprntPwr"),
            cumulative.get("reactPwr"),
            cumulative.get("whDlvdCum"),
            cumulative.get("whRcvdCum"),
            cumulative.get("varhLagCum"),
            cumulative.get("varhLeadCum"),
            cumulative.get("vahCum"),
            cumulative.get("rmsVoltage"),
            cumulative.get("rmsCurrent"),
            cumulative.get("pwrFactor"),
            cumulative.get("freqHz"),
        ))

    if not rows:
        return 0

    sql = """
        INSERT INTO meter_reports (
            collected_at, source_reading_time, report_type,
            current_power, active_power, apparent_power, reactive_power,
            wh_delivered_cumulative, wh_received_cumulative,
            varh_lag_cumulative, varh_lead_cumulative, vah_cumulative,
            rms_voltage, rms_current, power_factor, frequency
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """
    with conn.cursor() as cur:
        inserted = _execute_batch(cur, sql, rows)
    conn.commit()
    return inserted


def insert_inverter_readings(conn, data, collected_at):
    rows = []
    for inv in data:
        reading_time = inv.get("lastReportDate")
        if not reading_time:
            continue
        rows.append((
            collected_at,
            _ts(reading_time),
            inv["serialNumber"],
            inv.get("lastReportWatts"),
            inv.get("maxReportWatts"),
        ))

    if not rows:
        return 0

    sql = """
        INSERT INTO inverter_readings (
            collected_at, source_reading_time, serial_number, watts, max_watts
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """
    with conn.cursor() as cur:
        inserted = _execute_batch(cur, sql, rows)
    conn.commit()
    return inserted


def insert_poller_event(conn, event_type, severity, endpoint=None,
                        http_status=None, latency_ms=None, duration_seconds=None,
                        production_wh_missed=None, net_wh_missed=None, details=None):
    sql = """
        INSERT INTO poller_events (
            event_type, endpoint, severity, http_status, latency_ms,
            duration_seconds, production_wh_missed, net_wh_missed, details
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (event_type, endpoint, severity, http_status, latency_ms,
                          duration_seconds, production_wh_missed, net_wh_missed, details))
    conn.commit()
