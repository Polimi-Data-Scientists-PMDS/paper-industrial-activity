"""Named areas of interest defined in config.yaml.

"""
import yaml

from .params import CONFIG


def get_region(name, config=CONFIG):
    """Return the settings of a named region (bbox, srid)."""
    with open(config) as f:
        regions = yaml.safe_load(f)["regions"]
    if name not in regions:
        choices = ", ".join(regions)
        raise SystemExit(f"Unknown region '{name}', choose from: {choices}")
    return regions[name]


def to_corners(bbox):
    """[lon_min, lat_min, lon_max, lat_max] -> corners [ll, ul, ur, lr]."""
    x1, y1, x2, y2 = bbox
    return [[x1, y1], [x1, y2], [x2, y2], [x2, y1]]
