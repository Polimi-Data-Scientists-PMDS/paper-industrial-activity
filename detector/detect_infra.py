"""Detect fixed infrastructure from multi-month Sentinel-1 composites.

Stationary objects (wind turbines, platforms) persist in a median composite,
while moving vessels are averaged out. A composite is built for each time
window and each 1x1 degree tile of the region, and its detections are
exported as GeoJSON to Cloud Storage. Run it once per region; it takes
several hours on Earth Engine.

Example (four 6-month windows centred on Sep, Oct, Nov and Dec 2025):
    python detector/detect_infra.py --region denmark --start 2025-09-01 --windows 4

Modified by the PMDS Illegal Fishing Detector team (2026): command-line
interface with named regions; the region is tiled internally.

"""
import argparse

from core.detector import DetectorInfra
from core.gee import initialize
from core.params import Params
from core.ranges import window_range
from core.regions import get_region, to_corners

# CFAR parameters for composite (fixed infrastructure) detection
INFRA_PARAMS = dict(
    suffix="_window",
    thresholdx=21,
    resolution=20,
    window_inner=140,
    window_outer=200,
    dialation_radius=45,
    max_num_images=40,
    min_num_images=5,
    tile_dx=1,
    tile_dy=1,
)


def get_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--region", required=True, help="region name in config.yaml")
    parser.add_argument(
        "--start", required=True, help="centre of the first window, YYYY-MM-DD"
    )
    parser.add_argument(
        "--windows", type=int, default=4, help="number of windows, one month apart"
    )
    parser.add_argument(
        "--months", type=int, default=6, help="length of each window in months"
    )
    parser.add_argument("--folder", default="runs", help="where PARAMS files go")
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

    windows = list(window_range(args.start, args.windows, args.months))
    print(f"{len(windows)} composites over {args.region}:")
    for date1, date2 in windows:
        print(f"  {date1} to {date2}")

    if not args.yes:
        answer = input("Build composites and export detections? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            return

    initialize(defaults.project_id)

    for date1, date2 in windows:
        DetectorInfra(
            region=to_corners(region["bbox"]),
            region_id=args.region.upper(),
            region_name=args.region,
            window_date=[date1, date2],
            **INFRA_PARAMS,
        ).process(folder=args.folder)


if __name__ == "__main__":
    main()
