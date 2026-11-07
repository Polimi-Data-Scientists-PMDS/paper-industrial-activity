-- PostGIS schema for the SAR detection pipeline.
-- Safe to run repeatedly: objects are only created if they do not exist.

CREATE EXTENSION IF NOT EXISTS postgis;

-- One row per detection in a single Sentinel-1 scene.
-- Contains vessels and fixed structures until flag_infrastructure.py runs.
CREATE TABLE IF NOT EXISTS sar_detections (
    detect_id   text             NOT NULL,
    run_id      text             NOT NULL,  -- detector parameter set (GCS subbucket)
    region      text             NOT NULL,
    scene_id    text             NOT NULL,
    start_time  timestamp        NOT NULL,  -- scene acquisition window, UTC
    end_time    timestamp        NOT NULL,
    detect_lon  double precision NOT NULL,
    detect_lat  double precision NOT NULL,
    geom        geometry(Point, 4326)
                GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(detect_lon, detect_lat), 4326)) STORED,
    is_vessel   boolean,                    -- NULL until flag_infrastructure.py runs
    PRIMARY KEY (run_id, detect_id)
);

CREATE INDEX IF NOT EXISTS sar_detections_geom_idx
    ON sar_detections USING gist (geom);
CREATE INDEX IF NOT EXISTS sar_detections_region_time_idx
    ON sar_detections (region, start_time);

-- One row per detection in a multi-month median composite (fixed structures).
CREATE TABLE IF NOT EXISTS composite_detections (
    detect_id    text             NOT NULL,
    run_id       text             NOT NULL,
    region       text             NOT NULL,
    tile_id      text             NOT NULL,
    window_start date             NOT NULL,
    window_end   date             NOT NULL,
    detect_lon   double precision NOT NULL,
    detect_lat   double precision NOT NULL,
    geom         geometry(Point, 4326)
                 GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(detect_lon, detect_lat), 4326)) STORED,
    PRIMARY KEY (run_id, detect_id)
);

CREATE INDEX IF NOT EXISTS composite_detections_geom_idx
    ON composite_detections USING gist (geom);

-- Composite detections that persist across time windows:
-- wind turbines, oil and gas platforms, other permanent structures.
CREATE TABLE IF NOT EXISTS stable_infrastructure (
    infra_id   serial  PRIMARY KEY,
    region     text    NOT NULL,
    n_windows  integer NOT NULL,  -- number of windows the structure was seen in
    geom       geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS stable_infrastructure_geom_idx
    ON stable_infrastructure USING gist (geom);

-- Scene detections that are not fixed infrastructure.
CREATE OR REPLACE VIEW vessels AS
SELECT detect_id, run_id, region, scene_id, start_time, end_time,
       detect_lon, detect_lat, geom
FROM sar_detections
WHERE is_vessel;
