# Running the detector on public Earth Engine assets

The original detector depends on two Earth Engine assets owned by a Global
Fishing Watch account. Outside that account they return *Asset not found*,
so the pipeline cannot run. This fork replaces them with public datasets and
computes what the private assets used to provide.

## What the private assets provided

| Asset | Used for | Replacement |
|---|---|---|
| Ocean polygon (`ne_110m_ocean`) | Selecting scenes that touch the ocean | `GLOBAL_OCEAN`: a world rectangle, plus a region filter |
| Ocean/land raster with distance-to-shore bands `b1`, `b2`, … (km) | Masking land and a coastal buffer in each scene | MODIS `MOD44W` water mask, buffer computed on the fly |

Public polygon datasets such as `USDOS/LSIB` were tried for scene selection,
but they have too many vertices for a global filter and fail with
*Geometry has too many edges*. A rectangle is enough at that step, because
land is removed later, pixel by pixel, by the water raster.

## How the shore buffer is computed

`get_water_raster` in `detector/core/gee.py`:

1. Loads the water mask (MODIS `MOD44W`, 2015, 1 = water) or JRC Global
   Surface Water (`max_extent`). The original GFW asset is still supported.
2. Clips it to the scene or composite tile being processed.
3. Erodes the water area by `shore_buffer` km with `focal_min`, so detections
   within that distance of the coast are dropped.

Two choices keep this within Earth Engine's limits:

- **Clip before eroding.** Only the current scene or tile is processed,
  instead of the whole globe.
- **Erode at 250 m, apply at 20 m.** The buffer is computed on a 250 m grid
  and resampled bilinearly onto the 20 m SAR pixels. That is about 150 times
  fewer pixels than eroding at native resolution, and avoids
  *Computation timed out* errors.

## Settings

In `detector/config.yaml`:

```yaml
ocean_vector_uri: GLOBAL_OCEAN
ocean_raster_uri: MODIS/006/MOD44W   # or JRC/GSW1_4/GlobalSurfaceWater
shore_buffer: 1                      # km
```
