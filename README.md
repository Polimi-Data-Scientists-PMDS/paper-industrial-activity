# Sentinel-1 Vessel Detection

Detects vessels and offshore infrastructure in Sentinel-1 radar (SAR)
imagery on Google Earth Engine, and loads the detections into PostGIS with
fixed structures filtered out.

This is the SAR component of the Illegal Fishing Detector project. It is a
fork of Global Fishing Watch's
[paper-industrial-activity](https://github.com/GlobalFishingWatch/paper-industrial-activity)
(Paolo et al., *Nature*, 2024), reduced to the detection stage and adapted to
run outside Global Fishing Watch's infrastructure.

## Pipeline

```
Sentinel-1 GRD scenes (Earth Engine)
 ├─ detect_infra.py     CFAR on multi-month composites (once per region)
 └─ detect_vessels.py   CFAR on each scene of a day
          │
          ▼
GeoJSON in Cloud Storage
          │  load_detections.py
          ▼
PostGIS: composite_detections, sar_detections
          │  flag_infrastructure.py
          ▼
stable_infrastructure + is_vessel  →  view `vessels`
```

Detection uses a CFAR (constant false alarm rate) algorithm: a pixel is a
candidate when it is much brighter than the sea clutter in a ring around it.
Moving vessels average out of a multi-month median composite while wind
turbines and platforms remain, so detections that persist across composites
are treated as fixed infrastructure and removed from the daily detections.

## What this fork changes

| Area | Global Fishing Watch original | This fork |
|---|---|---|
| Land mask | Private Earth Engine assets with precomputed distance-to-shore bands | Public MODIS water mask, shore buffer computed on the fly ([details](docs/gee-public-assets.md)) |
| Area | Global | Named regions in `config.yaml` |
| Storage | BigQuery, one table per day | PostgreSQL/PostGIS, one table per detection type, idempotent loads |
| Vessels vs. infrastructure | Separate classification models | Persistence across composites, clustered in PostGIS (`ST_ClusterDBSCAN`) |
| Interface | Example scripts edited by hand | Command-line scripts |
| Scope | Detection, deep learning classifiers, AIS matching, paper analyses | Detection only |

The full list is in [NOTICE](NOTICE).

## Results: Denmark, 1 July 2025

| | |
|---|---|
| Area | 7–15°E, 53–57°N |
| Scene detections | 2,143 in 8 Sentinel-1 scenes |
| Composite detections | 7,134 in four 6-month windows (June 2025 to March 2026) |
| Stable infrastructure | 1,750 structures seen in at least 3 windows |
| Vessels | 876 detections more than 200 m from any structure |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login
earthengine authenticate
cp .env.example .env            # fill in project, bucket, database URL
set -a; source .env; set +a

python detector/detect_infra.py --region denmark --start 2025-09-01 --windows 4   # once per region
python detector/detect_vessels.py --region denmark --start 2025-07-01
python detector/load_detections.py runs/PARAMS_*.json
python detector/flag_infrastructure.py --region denmark
```

Setup, outputs, database tables and thresholds: [docs/pipeline.md](docs/pipeline.md).

## Repository layout

```
detector/
  config.yaml              default parameters and named regions
  detect_vessels.py        stage 1: vessel detection per day
  detect_infra.py          stage 1: infrastructure detection on composites
  load_detections.py       stage 2: Cloud Storage -> PostGIS
  flag_infrastructure.py   stage 3: vessels vs. fixed infrastructure
  core/                    detector classes and Earth Engine helpers
sql/schema.sql             database tables and the `vessels` view
docs/                      pipeline guide, Earth Engine asset notes
```

## Limitations

- No vessel/noise classifier is applied, so some detections are sea clutter
  or image artefacts.
- New or temporary structures can pass as vessels, and vessels moored next to
  a structure are removed.
- Detection times are the scene acquisition window (about 25 s), not the
  exact time of each detection.

## Credits and license

Original detector and paper by Global Fishing Watch:
Paolo et al. (2024), *Satellite mapping reveals extensive industrial activity
at sea*, Nature, <https://doi.org/10.1038/s41586-023-06825-8>.

Licensed under Apache 2.0 for noncommercial use only (CC BY-NC 4.0), as the
original. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
