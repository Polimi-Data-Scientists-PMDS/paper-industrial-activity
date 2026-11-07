"""Detect vessels in Sentinel-1 scenes over a region, one day at a time.

Each scene is processed on Google Earth Engine and its detections are
exported as GeoJSON to Cloud Storage:

    gs://<bucket>/<version>/<subbucket>/<YYYYMMDD>/<scene_id>.geojson

One PARAMS_*.json file per day is written to `runs/`; pass it to
load_detections.py to move the detections into PostGIS.

Example:
    python detector/detect_vessels.py --region denmark --start 2025-07-01

Modified by the PMDS Illegal Fishing Detector team (2026): command-line
interface with named regions, scene listing and confirmation before export.

"""
import argparse

from core.detector import DetectorVessel
from core.gee import initialize
from core.params import Params
from core.ranges import date_range
from core.regions import get_region, to_corners

# CFAR parameters for single-scene vessel detection
VESSEL_PARAMS = dict(
    thresholdx=22,
    resolution=20,
    window_inner=200,
    window_outer=600,
    dialation_radius=60,
)


def get_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--region", required=True, help="region name in config.yaml")
    parser.add_argument("--start", required=True, help="first day, YYYY-MM-DD")
    parser.add_argument("--end", help="last day, YYYY-MM-DD (default: --start)")
    parser.add_argument(
        "--satellite",
        choices=["both", "S1A", "S1B"],
        default="both",
        help="Sentinel-1 unit(s) to use",
    )
    parser.add_argument("--folder", default="runs", help="where PARAMS files go")
    parser.add_argument(
        "--dry-run", action="store_true", help="list scenes and exit"
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="export without asking"
    )
    return parser.parse_args()


def main():
    args = get_args()
    region = get_region(args.region)

    defaults = Params()
    if not (defaults.project_id and defaults.bucket):
        raise SystemExit("Set GCP_PROJECT and GCS_BUCKET (see .env.example)")
    initialize(defaults.project_id)

    satellite = "" if args.satellite == "both" else args.satellite

    for date in date_range(args.start, args.end or args.start):
        detector = DetectorVessel(
            date=date,
            satellite=satellite,
            region=to_corners(region["bbox"]),
            region_name=args.region,
            **VESSEL_PARAMS,
        )

        scenes = detector.get_scenes()
        print(f"{date}: {len(scenes)} scenes over {args.region}")
        for scene_id in scenes:
            print(f"  {scene_id}")

        if args.dry_run or not scenes:
            continue
        if not args.yes:
            answer = input("Export detections to Cloud Storage? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                print(f"{date}: skipped")
                continue

        detector.process(folder=args.folder, skip_done=True)


if __name__ == "__main__":
    main()
