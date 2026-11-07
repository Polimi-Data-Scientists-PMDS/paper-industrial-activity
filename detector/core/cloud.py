"""Google Cloud Storage helpers.

Modified by the PMDS Illegal Fishing Detector team (2026): reduced to the
GCS download used by the PostGIS loader (BigQuery and image helpers removed),
errors are raised instead of printed.

"""
import gcsfs


def download_from_gcs(rpath, lpath, project_id=None):
    """Download objects under `rpath` (wildcards allowed) to `lpath`."""
    fs = gcsfs.GCSFileSystem(project=project_id, token="google_default")
    out = fs.get(rpath, lpath, recursive=True) or []
    print(f"{len(out)} files downloaded from GCS")
    return out
