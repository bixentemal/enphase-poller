import logging
import signal
import threading
import time
from datetime import datetime, timezone

import uvicorn

from poller import client, storage
from poller.api import app
from poller.config import (
    API_PORT,
    ENABLE_CHANNEL_READINGS,
    INVERTER_POLL_INTERVAL,
    METER_REPORT_POLL_INTERVAL,
    POLL_INTERVAL,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("enphase-poller")

_running = True


def _handle_signal(sig, frame):
    global _running
    log.info("Received signal %s, shutting down", sig)
    _running = False


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


class GapTracker:
    """Tracks polling gaps for /ivp/meters/reports only.

    Gap detection is only meaningful for endpoints with monotonic cumulative
    counters. Other endpoint failures are logged as errors but do not
    constitute energy gaps.
    """

    def __init__(self):
        self.last_cumulatives = {}  # report_type -> {delivered, received}
        self.gap_start = None
        self.in_gap = False

    def record_success(self, reports_data):
        for report in reports_data:
            cumulative = report.get("cumulative", {})
            report_type = report.get("reportType")
            if report_type and cumulative:
                self.last_cumulatives[report_type] = {
                    "delivered": cumulative.get("whDlvdCum"),
                    "received": cumulative.get("whRcvdCum"),
                }

    def enter_gap(self, conn):
        if not self.in_gap:
            self.gap_start = datetime.now(timezone.utc)
            self.in_gap = True
            storage.insert_poller_event(
                conn,
                event_type="gap_start",
                severity="warning",
                endpoint="/ivp/meters/reports",
                details=f"Gap started at {self.gap_start.isoformat()}",
            )

    def exit_gap(self, conn, reports_data):
        if not self.in_gap:
            return
        self.in_gap = False
        gap_end = datetime.now(timezone.utc)
        duration = int((gap_end - self.gap_start).total_seconds())

        production_missed = None
        net_missed = None

        for report in reports_data:
            cumulative = report.get("cumulative", {})
            report_type = report.get("reportType")
            prev = self.last_cumulatives.get(report_type)
            if prev and cumulative:
                delivered_now = cumulative.get("whDlvdCum")
                if report_type == "production" and delivered_now and prev.get("delivered"):
                    production_missed = delivered_now - prev["delivered"]
                if report_type == "net-consumption" and delivered_now and prev.get("delivered"):
                    net_missed = delivered_now - prev["delivered"]

        storage.insert_poller_event(
            conn,
            event_type="gap_end",
            severity="warning",
            endpoint="/ivp/meters/reports",
            duration_seconds=duration,
            production_wh_missed=production_missed,
            net_wh_missed=net_missed,
            details=f"Gap from {self.gap_start.isoformat()} to {gap_end.isoformat()}",
        )
        log.warning(
            "Gap recovered: %ds, production_wh_missed=%.1f",
            duration,
            production_missed or 0,
        )


def _log_poll_error(conn, endpoint, error):
    """Log poll failure to both stdout and poller_events."""
    log.error("Failed to poll %s: %s", endpoint, error)
    try:
        storage.insert_poller_event(
            conn,
            event_type="error",
            severity="error",
            endpoint=endpoint,
            details=str(error),
        )
    except Exception as e:
        log.error("Failed to write error event: %s", e)


def _poll_loop():
    conn = storage.get_connection()
    storage.bootstrap_schema(conn)

    meter_types = client.fetch_meter_types()
    log.info("Meter types: %s", meter_types)

    storage.insert_poller_event(conn, "startup", "info", details="Poller started")
    log.info(
        "Started: poll=%ds, meters_report=%ds, inverters=%ds",
        POLL_INTERVAL, METER_REPORT_POLL_INTERVAL, INVERTER_POLL_INTERVAL,
    )

    gap_tracker = GapTracker()
    last_production = 0
    last_meter_readings = 0
    last_meter_reports = 0
    last_inverters = 0

    while _running:
        now = time.monotonic()
        collected_at = datetime.now(timezone.utc)

        # /production.json — every POLL_INTERVAL
        if now - last_production >= POLL_INTERVAL:
            try:
                data, latency = client.fetch_production()
                inserted = storage.insert_production_overview(conn, data, collected_at)
                log.info("production_overview: %d inserted, %dms", inserted, latency)
                last_production = now
            except Exception as e:
                _log_poll_error(conn, "/production.json", e)

        # /ivp/meters/readings — every POLL_INTERVAL
        if now - last_meter_readings >= POLL_INTERVAL:
            try:
                data, latency = client.fetch_meter_readings()
                mr, mc = storage.insert_meter_readings(conn, data, meter_types, collected_at, ENABLE_CHANNEL_READINGS)
                log.info("meter_readings: %d inserted, channels: %d inserted, %dms", mr, mc, latency)
                last_meter_readings = now
            except Exception as e:
                _log_poll_error(conn, "/ivp/meters/readings", e)

        # /ivp/meters/reports — every METER_REPORT_POLL_INTERVAL
        # Gap tracking is scoped to this endpoint only (cumulative counters)
        if now - last_meter_reports >= METER_REPORT_POLL_INTERVAL:
            try:
                data, latency = client.fetch_meter_reports()
                inserted = storage.insert_meter_reports(conn, data, collected_at)
                log.info("meter_reports: %d inserted, %dms", inserted, latency)
                if gap_tracker.in_gap:
                    gap_tracker.exit_gap(conn, data)
                gap_tracker.record_success(data)
                last_meter_reports = now
            except Exception as e:
                _log_poll_error(conn, "/ivp/meters/reports", e)
                gap_tracker.enter_gap(conn)

        # /api/v1/production/inverters — every INVERTER_POLL_INTERVAL
        if now - last_inverters >= INVERTER_POLL_INTERVAL:
            try:
                data, latency = client.fetch_inverters()
                inserted = storage.insert_inverter_readings(conn, data, collected_at)
                log.info("inverter_readings: %d inserted, %dms", inserted, latency)
                last_inverters = now
            except Exception as e:
                _log_poll_error(conn, "/api/v1/production/inverters", e)

        time.sleep(1)

    storage.insert_poller_event(conn, "shutdown", "info", details="Poller stopped")
    conn.close()
    log.info("Poll loop shutdown complete")


def main():
    poller_thread = threading.Thread(target=_poll_loop, daemon=True)
    poller_thread.start()
    log.info("API server starting on port %d", API_PORT)
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
