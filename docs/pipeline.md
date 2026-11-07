# Pipeline guide

The pipeline has three stages: detection on Google Earth Engine, loading into
PostGIS, and separating vessels from fixed infrastructure.

```
Sentinel-1 GRD scenes (Earth Engine)
 ├─ detect_infra.py     CFAR on multi-month composites (once per region)
 └─ detect_vessels.py   CFAR on each scene of a day
          │
          ▼
GeoJSON files in Cloud Storage   +   PARAMS_*.json run records in runs/
          │
          │  load_detections.py
          ▼
PostGIS: composite_detections, sar_detections
          │
          │  flag_infrastructure.py
          ▼
stable_infrastructure, sar_detections.is_vessel  →  view `vessels`
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

gcloud auth application-default login   # Cloud Storage
earthengine authenticate                # Earth Engine

cp .env.example .env                    # then fill in the three values
set -a; source .env; set +a
```

The Google Cloud project must have the Earth Engine API enabled, and the
bucket must be writable by that project.

### Database connection

The database is not exposed to the internet. Open an SSH tunnel and leave it
running in its own terminal:

```bash
ssh -N -L 5433:localhost:5432 <ssh-user>@<server>
```

Then point `DATABASE_URL` at `localhost:5433`. The loader creates the tables
on first use (`sql/schema.sql`); the database user needs permission to
create tables, or an administrator runs that file once.

## 1. Detection on Earth Engine

### Fixed infrastructure (once per region)

```bash
python detector/detect_infra.py --region denmark --start 2025-09-01 --windows 4
```

Builds one median composite per time window and 1x1 degree tile. With
`--windows 4 --months 6` the windows are centred one month apart, which
gives four overlapping 6-month windows. Moving vessels average out of a
median composite; stationary structures remain. Expect several hours.

### Vessels (per day)

```bash
python detector/detect_vessels.py --region denmark --start 2025-07-01 --dry-run   # list scenes
python detector/detect_vessels.py --region denmark --start 2025-07-01 --end 2025-07-07
```

Finds the Sentinel-1 IW scenes (VV+VH, high resolution) over the region,
masks land and a 1 km coastal buffer, and runs the CFAR detector on the VH
band. The command waits until the Earth Engine export tasks finish and
prints their progress.

### Outputs

- GeoJSON per scene or tile:
  `gs://<bucket>/<version>/<subbucket>/<YYYYMMDD>/<scene_id>.geojson`
- A record of every run in `runs/`: `PARAMS_<subbucket>_<YYYYMMDD>[_<REGION>].json`
  (all parameters, the code commit) and `SCENES_….json` (processed and failed
  scenes).

The **subbucket** encodes the detector parameters, e.g.
`20m_22x_200i_600o_60d_ad` = 20 m resolution, threshold 22x, inner/outer
window radius 200/600 m, dilation radius 60 m, ascending and descending orbits. It is stored
as `run_id` in the database, so different parameter sets can coexist.

Region names and boxes are set in `detector/config.yaml` under `regions`.

## 2. Loading into PostGIS

```bash
python detector/load_detections.py runs/PARAMS_*.json
```

For each PARAMS file, downloads the GeoJSONs into a temporary folder and
writes one row per detection, with a PostGIS point geometry:

| Run type | Table | Time columns |
|---|---|---|
| Scene (vessels) | `sar_detections` | `start_time`, `end_time`: scene acquisition window, UTC, about 25 s |
| Composite (infrastructure) | `composite_detections` | `window_start`, `window_end` |

Loading is idempotent: rows of the same run and scenes are replaced, so a
file can be loaded again safely.

Already downloaded GeoJSONs can be loaded without Cloud Storage. PARAMS files
written before regions were named also need `--region`:

```bash
python detector/load_detections.py --local-dir data/detections --region denmark params/PARAMS_*_20250701.json
```

## 3. Separating vessels from infrastructure

```bash
python detector/flag_infrastructure.py --region denmark
```

1. Clusters the composite detections of the region with DBSCAN
   (`ST_ClusterDBSCAN`), in the metric projection set for the region.
2. Keeps clusters seen in at least `--min-windows` windows (default 3) as
   `stable_infrastructure`.
3. Sets `is_vessel` on every scene detection of the region: false if it lies
   within `--distance` metres of stable infrastructure (default 200 m).

The `vessels` view returns the detections with `is_vessel = true`.

| Option | Default | Effect |
|---|---|---|
| `--eps` | 200 m | Max distance between composite detections of one structure |
| `--min-windows` | 3 | Windows a structure must appear in |
| `--distance` | 200 m | Max distance from a structure to drop a detection |

On Denmark, 2025-07-01, the number of vessels changes little between 130 m
and 250 m (877 to 872 of 2,143), and rises quickly below 100 m.

## Example queries

```sql
-- Vessels of one day
SELECT detect_id, detect_lon, detect_lat, start_time
FROM vessels
WHERE region = 'denmark' AND start_time::date = '2025-07-01';

-- Vessels inside a box (lon_min, lat_min, lon_max, lat_max)
SELECT * FROM vessels
WHERE geom && ST_MakeEnvelope(7.5, 53.5, 9.0, 55.0, 4326);
```
