"""Separate vessels from fixed infrastructure in PostGIS.

1. Cluster the composite detections of a region (DBSCAN, distances in metres).
2. Keep the clusters seen in at least N time windows: stable infrastructure.
3. Mark each scene detection of the region as a vessel unless it lies
   within a given distance of stable infrastructure.

Re-running replaces the stable infrastructure of the region and recomputes
the flag, so thresholds can be tuned freely.

Example:
    python detector/flag_infrastructure.py --region denmark
"""
import argparse
import os

from sqlalchemy import create_engine, text

from core.regions import get_region

CLUSTER_SQL = """
INSERT INTO stable_infrastructure (region, n_windows, geom)
SELECT :region,
       count(DISTINCT window_start),
       ST_Transform(ST_Centroid(ST_Collect(geom_m)), 4326)
FROM (
    SELECT window_start,
           ST_Transform(geom, :srid) AS geom_m,
           ST_ClusterDBSCAN(ST_Transform(geom, :srid), :eps, 1) OVER () AS cluster_id
    FROM composite_detections
    WHERE region = :region
) AS clustered
GROUP BY cluster_id
HAVING count(DISTINCT window_start) >= :min_windows
"""

FLAG_SQL = """
UPDATE sar_detections AS d
SET is_vessel = NOT EXISTS (
    SELECT 1
    FROM stable_infrastructure AS s
    WHERE s.region = d.region
      AND ST_DWithin(s.geom::geography, d.geom::geography, :distance)
)
WHERE d.region = :region
"""

SUMMARY_SQL = """
SELECT count(*) FILTER (WHERE is_vessel), count(*)
FROM sar_detections
WHERE region = :region
"""


def get_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--region", required=True, help="region name in config.yaml")
    parser.add_argument(
        "--db",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL URL (default: DATABASE_URL)",
    )
    parser.add_argument(
        "--eps",
        type=float,
        default=200,
        help="clustering distance between composite detections (m)",
    )
    parser.add_argument(
        "--min-windows",
        type=int,
        default=3,
        help="windows a cluster must appear in to count as infrastructure",
    )
    parser.add_argument(
        "--distance",
        type=float,
        default=200,
        help="max distance from infrastructure to drop a detection (m)",
    )
    args = parser.parse_args()
    if not args.db:
        parser.error("set DATABASE_URL or pass --db")
    return args


def main():
    args = get_args()
    region = get_region(args.region)
    engine = create_engine(args.db)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM stable_infrastructure WHERE region = :region"),
            {"region": args.region},
        )
        n_infra = conn.execute(
            text(CLUSTER_SQL),
            {
                "region": args.region,
                "srid": region["srid"],
                "eps": args.eps,
                "min_windows": args.min_windows,
            },
        ).rowcount
        conn.execute(
            text(FLAG_SQL), {"region": args.region, "distance": args.distance}
        )
        n_vessels, n_total = conn.execute(
            text(SUMMARY_SQL), {"region": args.region}
        ).one()

    print(f"{n_infra} stable infrastructure points in {args.region}")
    print(f"{n_vessels} of {n_total} scene detections flagged as vessels")


if __name__ == "__main__":
    main()
