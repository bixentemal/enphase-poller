import os


ENVOY_HOST = os.environ.get("ENVOY_HOST", "envoy.local")
ENPHASE_TOKEN = os.environ["ENPHASE_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))
INVERTER_POLL_INTERVAL = int(os.environ.get("INVERTER_POLL_INTERVAL", "300"))
METER_REPORT_POLL_INTERVAL = int(os.environ.get("METER_REPORT_POLL_INTERVAL", "60"))

ENABLE_CHANNEL_READINGS = os.environ.get("ENABLE_CHANNEL_READINGS", "false").lower() in ("true", "1", "yes")

ENVOY_BASE_URL = f"https://{ENVOY_HOST}"
