import logging
import time

import requests
import urllib3

from poller.config import ENVOY_BASE_URL, ENPHASE_TOKEN

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)

_session = requests.Session()
_session.headers["Authorization"] = f"Bearer {ENPHASE_TOKEN}"
_session.verify = False


def _get(path, timeout=10):
    url = f"{ENVOY_BASE_URL}{path}"
    start = time.monotonic()
    resp = _session.get(url, timeout=timeout)
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    return resp.json(), latency_ms


def fetch_production():
    return _get("/production.json")


def fetch_meter_readings():
    return _get("/ivp/meters/readings")


def fetch_meter_reports():
    return _get("/ivp/meters/reports")


def fetch_inverters():
    return _get("/api/v1/production/inverters")


def fetch_meter_types():
    """Fetch meter config to map eid -> measurementType."""
    data, _ = _get("/ivp/meters")
    return {m["eid"]: m["measurementType"] for m in data}
