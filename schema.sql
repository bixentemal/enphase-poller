CREATE TABLE IF NOT EXISTS production_overview (
    id BIGSERIAL PRIMARY KEY,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_reading_time TIMESTAMPTZ NOT NULL,
    source_type TEXT NOT NULL,
    active_count INT,
    w_now DOUBLE PRECISION,
    wh_lifetime DOUBLE PRECISION,
    wh_today DOUBLE PRECISION,
    wh_last_seven_days DOUBLE PRECISION,
    vah_lifetime DOUBLE PRECISION,
    vah_today DOUBLE PRECISION,
    varh_lead_lifetime DOUBLE PRECISION,
    varh_lead_today DOUBLE PRECISION,
    varh_lag_lifetime DOUBLE PRECISION,
    varh_lag_today DOUBLE PRECISION,
    rms_current DOUBLE PRECISION,
    rms_voltage DOUBLE PRECISION,
    reactive_power DOUBLE PRECISION,
    apparent_power DOUBLE PRECISION,
    power_factor DOUBLE PRECISION,
    wh_now DOUBLE PRECISION,
    state TEXT,
    UNIQUE(source_reading_time, source_type)
);

CREATE TABLE IF NOT EXISTS meter_readings (
    id BIGSERIAL PRIMARY KEY,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_reading_time TIMESTAMPTZ NOT NULL,
    meter_eid BIGINT NOT NULL,
    meter_type TEXT NOT NULL,
    active_power DOUBLE PRECISION,
    apparent_power DOUBLE PRECISION,
    reactive_power DOUBLE PRECISION,
    voltage DOUBLE PRECISION,
    current_a DOUBLE PRECISION,
    frequency DOUBLE PRECISION,
    power_factor DOUBLE PRECISION,
    act_energy_delivered DOUBLE PRECISION,
    act_energy_received DOUBLE PRECISION,
    apparent_energy DOUBLE PRECISION,
    reactive_energy_lag DOUBLE PRECISION,
    reactive_energy_lead DOUBLE PRECISION,
    UNIQUE(source_reading_time, meter_eid)
);

CREATE TABLE IF NOT EXISTS meter_reading_channels (
    id BIGSERIAL PRIMARY KEY,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_reading_time TIMESTAMPTZ NOT NULL,
    meter_eid BIGINT NOT NULL,
    channel_eid BIGINT NOT NULL,
    active_power DOUBLE PRECISION,
    apparent_power DOUBLE PRECISION,
    reactive_power DOUBLE PRECISION,
    voltage DOUBLE PRECISION,
    current_a DOUBLE PRECISION,
    frequency DOUBLE PRECISION,
    power_factor DOUBLE PRECISION,
    act_energy_delivered DOUBLE PRECISION,
    act_energy_received DOUBLE PRECISION,
    apparent_energy DOUBLE PRECISION,
    reactive_energy_lag DOUBLE PRECISION,
    reactive_energy_lead DOUBLE PRECISION,
    UNIQUE(source_reading_time, channel_eid)
);

CREATE TABLE IF NOT EXISTS meter_reports (
    id BIGSERIAL PRIMARY KEY,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_reading_time TIMESTAMPTZ NOT NULL,
    report_type TEXT NOT NULL,
    current_power DOUBLE PRECISION,
    active_power DOUBLE PRECISION,
    apparent_power DOUBLE PRECISION,
    reactive_power DOUBLE PRECISION,
    wh_delivered_cumulative DOUBLE PRECISION,
    wh_received_cumulative DOUBLE PRECISION,
    varh_lag_cumulative DOUBLE PRECISION,
    varh_lead_cumulative DOUBLE PRECISION,
    vah_cumulative DOUBLE PRECISION,
    rms_voltage DOUBLE PRECISION,
    rms_current DOUBLE PRECISION,
    power_factor DOUBLE PRECISION,
    frequency DOUBLE PRECISION,
    UNIQUE(source_reading_time, report_type)
);

CREATE TABLE IF NOT EXISTS inverter_readings (
    id BIGSERIAL PRIMARY KEY,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_reading_time TIMESTAMPTZ NOT NULL,
    serial_number TEXT NOT NULL,
    watts DOUBLE PRECISION,
    max_watts DOUBLE PRECISION,
    UNIQUE(source_reading_time, serial_number)
);

CREATE TABLE IF NOT EXISTS poller_events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    endpoint TEXT,
    severity TEXT NOT NULL,
    http_status INT,
    latency_ms INT,
    duration_seconds INT,
    production_wh_missed DOUBLE PRECISION,
    net_wh_missed DOUBLE PRECISION,
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_production_overview_ts ON production_overview(source_reading_time);
CREATE INDEX IF NOT EXISTS idx_meter_readings_ts ON meter_readings(source_reading_time);
CREATE INDEX IF NOT EXISTS idx_meter_reading_channels_ts ON meter_reading_channels(source_reading_time);
CREATE INDEX IF NOT EXISTS idx_meter_reports_ts ON meter_reports(source_reading_time);
CREATE INDEX IF NOT EXISTS idx_inverter_readings_ts ON inverter_readings(source_reading_time);
CREATE INDEX IF NOT EXISTS idx_poller_events_ts ON poller_events(ts);
