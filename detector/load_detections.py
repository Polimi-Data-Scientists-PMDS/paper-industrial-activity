"""Load detection GeoJSONs exported by Earth Engine into PostGIS.

Reads the PARAMS_*.json files written by detect_vessels.py and
detect_infra.py, downloads the matching GeoJSONs from Cloud Storage (or
reads them from a local folder) and writes one row per detection:

    scene runs     -> sar_detections        (vessels and fixed structures)
    composite runs -> composite_detections  (fixed structures only)

Loading is idempotent: rows of the same run and scenes are replaced.

Examples:
    python detector/load_detections.py runs/PARAMS_*_20250701.json
    python detector/load_detections.py --local-dir data/detections runs/PARAMS_*_20250701.json

Adapted by the PMDS Illegal Fishing Detector team (2026) from the BigQuery
loader upload_detect.py: PostGIS target, schema created on first use,
temporary download folder, idempotent loads.

"""
import argparse
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from core.checks import validate_jsons
from core.cloud import download_from_gcs
from core.params import Params
from core.utils import get_detect_ids, get_times_from_scene, list_files

SCHEMA = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"


def get_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", help="PARAMS_*.json")
    parser.add_argument(
        "--db",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL URL (default: DATABASE_URL)",
    )
    parser.add_argument(
        "--local-dir",
        help="read GeoJSONs from this folder instead of Cloud Storage",
    )
    parser.add_argument(
        "--region",
        help="region name, for PARAMS files written before regions were named",
    )
    args = parser.parse_args()
    if not args.db:
        parser.error("set DATABASE_URL or pass --db")
    return args


def read_geojson(jfile):
    """GeoJSON of one scene or tile -> DataFrame of point detections."""
    with open(jfile) as f:
        features = json.load(f)["features"]
    coords = [ft["geometry"]["coordinates"] for ft in features]
    df = pd.DataFrame(coords, columns=["detect_lon", "detect_lat"])
    df.insert(0, "scene_id", Path(jfile).stem)
    return df


def fetch_files(params, local_dir, workdir):
    """Return the valid GeoJSONs of one run, local or from Cloud Storage."""
    ymd = params.date.replace("-", "")

    if local_dir:
        path = Path(local_dir)
        if (path / ymd).exists():
            path = path / ymd
    else:
        remote = f"{params.bucket}/{params.version}/{params.subbucket}/{ymd}"
        if params.region_id:
            remote += f"/*{params.region_id}*"
        path = Path(workdir) / ymd
        path.mkdir(parents=True)
        download_from_gcs(remote, f"{path}/", project_id=params.project_id)

    files = list_files(path, glob="*.geojson")
    if params.region_id:
        files = [f for f in files if params.region_id.upper() in Path(f).stem]
    return validate_jsons(files)


def to_rows(params, df, region):
    """Add the columns of the target table to the raw detections."""
    df["run_id"] = params.subbucket
    df["region"] = region
    df["detect_id"] = get_detect_ids(df.detect_lon, df.detect_lat, df.scene_id)

    if params.window_date:
        df = df.rename(columns={"scene_id": "tile_id"})
        df["window_start"], df["window_end"] = params.window_date
        return "composite_detections", "tile_id", df

    times = df.scene_id.map(get_times_from_scene)
    df["start_time"] = pd.to_datetime(times.str[0])
    df["end_time"] = pd.to_datetime(times.str[1])
    return "sar_detections", "scene_id", df


def load(engine, table, key, df):
    """Replace the rows of these scenes/tiles for this run, in one transaction."""
    with engine.begin() as conn:
        deleted = conn.execute(
            text(f"DELETE FROM {table} WHERE run_id = :run_id AND {key} = ANY(:ids)"),
            {"run_id": df.run_id.iat[0], "ids": list(df[key].unique())},
        ).rowcount
        df.to_sql(table, conn, if_exists="append", index=False)
    print(f"{len(df)} rows -> {table} ({deleted} replaced)")


def main():
    args = get_args()
    engine = create_engine(args.db)

    with engine.begin() as conn:
        conn.exec_driver_sql(SCHEMA.read_text())

    for pfile in args.files:
        params = Params(pfile)
        region = args.region or getattr(params, "region_name", None)
        if not region:
            raise SystemExit(f"{pfile}: no region recorded, pass --region")

        print(f"{Path(pfile).name} ({region})")
        with tempfile.TemporaryDirectory() as workdir:
            frames = [read_geojson(f) for f in fetch_files(params, args.local_dir, workdir)]
        frames = [df for df in frames if not df.empty]

        if not frames:
            print("No detections found, skipping")
            continue
        df = pd.concat(frames, ignore_index=True)
        load(engine, *to_rows(params, df, region))


if __name__ == "__main__":
    main()
