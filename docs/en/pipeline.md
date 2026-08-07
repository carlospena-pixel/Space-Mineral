# Pipeline

This document describes **the flow**: what runs, in what order, what goes in and
what comes out of each stage. Why each decision is what it is belongs in
[technical_decisions.md](technical_decisions.md), and is linked here rather than
repeated.

## Stage status

| # | Stage | Where it lives | Status |
|---|-------|----------------|--------|
| 0 | Scene acquisition | `io/acquisition.py` | **Manual**: `download_scene()` is a stub |
| 1 | Locate the product and its bands | `io/raster_io.py` | Implemented |
| 2 | Read the product's scaling | `preprocessing/reflectance.py` | Implemented |
| 3 | Crop to the AOI and resample to 20 m | `preprocessing/resampling.py` | Implemented |
| 4 | Scale DN to reflectance | `preprocessing/reflectance.py` | Implemented |
| 5 | Build the validity mask | `preprocessing/masking.py` | Implemented |
| 6 | Hand back and serialise the `Scene` | `preprocessing/scene_builder.py`, `io/raster_io.py` | Implemented |
| 7 | Reference signature and visual comparison | `spectral/endmembers.py`, `visualization/spectra.py` | Implemented |
| 8 | Detection algorithm | `algorithms/sam.py` | Detector implemented, **no orchestrator** |
| 9 | Validation against geological mapping | `validation/` | **Pending, Tier 1** |
| 10 | Result visualisation | `visualization/maps.py` | **Pending, Tier 1** |

Stages 1 to 6 are the preprocessing that Week 2 closed, and a single function
chains them: `build_scene_from_safe()`. `pipeline.py` — the orchestrator for the
whole project, the one that would cover stages 7 to 10 — still raises
`NotImplementedError`.

## The implemented flow: from `.SAFE` to `Scene`

```
data/raw/<scene>.SAFE
   |
   |-- find_safe_dir(root) ................ product path
   |-- read_l2a_scaling(safe_dir) ......... baseline, offset, quantification
   |-- find_band_file(safe_dir, band) ..... .jp2 path + native resolution
   |
   v
read_band_on_grid(path, bounds, target_shape, resampling_for(...))
   |      crops to the AOI window and returns the band already at 20 m
   |
   +---- for each BAND_ORDER band --------+       +---- SCL band ----+
   |                                      |       |                  |
   v                                      |       v                  |
dn_to_reflectance(DN, offset, quant.)     |   build_cloud_mask(SCL, classes)
   |      float32 in [0,1], NaN = no data |       |   True = valid pixel
   v                                      |       v
cube (12, height, width) -----------------+--> mask = mask_scl & ~isnan(cube).any(0)
   |
   v
Scene(cube, band_names, transform, crs, mask, meta)
   |
   +-- save_scene ---> data/interim/scene.npz
```

### 0. Scene acquisition

**Manual today.** `io/acquisition.py::download_scene()` and its CLI
`scripts/download_scene.py` exist as scaffolding and raise
`NotImplementedError`. The product is downloaded by hand from the
[Copernicus Data Space](https://dataspace.copernicus.eu/) and unpacked into
`data/raw/`, leaving the full `S2B_MSIL2A_..._T19KDT_....SAFE` folder (a `.SAFE`
is a directory, not a file). Nothing under `data/` is versioned.

The one exception is `data/external/`, home of the kaolinite reference signature
(`S07SNTL2_Kaolinite_CM9_BECKb_AREF.txt`, from USGS Spectral Library 7): it is a
small `.txt` and it *is* versioned, so the team can run the `spectral/` tests
without downloading anything.

**In**: nothing automated. **Out**: `data/raw/<scene>.SAFE`.

### 1. Locate the product and its bands

**Functions**: `find_safe_dir(root)` and `find_band_file(safe_dir, band,
prefer)`, in `io/raster_io.py`.

**In**: a root directory (`data/raw/`) and a canonical band name (`"B1"`,
`"B8A"`, `"SCL"`).

**Out**: the `.SAFE` path, and per band the `.jp2` path together with its
**native resolution** in metres.

**The non-obvious decision**: `find_band_file` does not assume where each band
lives; it looks in the `R20m`, `R10m` and `R60m` folders in that order and
returns the first hit. An L2A product publishes several bands resampled to
several resolutions, and the native one — the only one that did not go through
an ESA resampling — depends on the band: B8 only exists at 10 m, B9 only at
60 m, the rest at 20 m. Always preferring 20 m avoids resampling what is already
on the target grid, and returning the resolution found is what lets stage 3 pick
the right resampling method. Each band's resolution is recorded in
`Scene.meta["bands_source"]`.

The translation between the canonical name without a leading zero (`B1`) and the
file token with one (`B01`) lives in `BAND_TOKEN`, generated from `BAND_ORDER`
([technical decisions §2](technical_decisions.md#band_order--12-bands)).

### 2. Read the product's scaling

**Function**: `read_l2a_scaling(safe_dir)`, in `preprocessing/reflectance.py`.

**In**: the `.SAFE` path.

**Out**: `(baseline, offset, quantification)`. For this scene:
`("05.11", -1000.0, 10000.0)`.

**The non-obvious decision**: all three values are **read from
`MTD_MSIL2A.xml`** rather than hard-coded. They depend on which version ESA used
to process the product, and a reprocessed scene can change them with nothing
else changing; hard-coding works until the day it does not, and the failure is a
constant bias in reflectance, not an exception. If the XML is missing, the
fallback `("04.00", -1000.0, 10000.0)` is used with an explicit
`warnings.warn`.

Why the offset exists and what applying the old formula costs:
[technical decisions §6](technical_decisions.md#6-reflectance).

### 3. Crop to the AOI and resample to 20 m

**Functions**: `resampling_for(src_res_m, target_res_m, categorical)` and
`read_band_on_grid(path, bounds, target_shape, resampling, expected_crs)`, in
`preprocessing/resampling.py`. The AOI window is resolved beforehand by
`_resolver_ventana()` in `scene_builder.py`.

**In**: the `.jp2` path, the AOI `bounds` in the tile's CRS (EPSG:32719), the
target shape in pixels and the resampling method.

**Out**: a 2D array with exactly the target shape and the file's native dtype
(integers).

The AOI can be requested three ways: `None` uses `DEFAULT_AOI_WINDOW`
(`col_off=1000, row_off=1000, 2000×2000` px at 20 m, i.e. 40 × 40 km); a
`Window` is used as is; a WGS84 bbox is reprojected with `transform_bounds` and
rounded to whole pixels. An AOI that misses the tile is a `ValueError`; one that
only partly overlaps is cropped with a warning.

**There are two non-obvious decisions**:

1. **Resampling happens at read time**, not on an assembled `Scene`: the AOI is
   translated into a window on each band's native grid and GDAL is asked to
   deliver it already shaped to the target. The cube is born homogeneous at
   20 m and never exists with mixed-resolution bands.
2. **SCL is read with `nearest` and never with `average`.** It is the only band
   requested with `categorical=True`, which is what `scene_builder.py` does when
   reading it. SCL is a per-pixel label, not a measurement: the average of
   "water" (6) and "unclassified" (7) is 6.5, which rounds to one or the other
   depending on the luck of the rounding, and the average of "bare soil" (5) and
   "high-probability cloud" (9) is 7. None of those classes was there. The
   mistake raises nothing: it returns a plausible, wrong mask, which is the
   worst way to be wrong. `resampling_for` settles it before even looking at the
   resolutions, so there is no path in which a categorical band ends up
   interpolated.

Which method applies in each case, and the premise that makes cropping by
coordinates without `warp` valid:
[technical decisions §5](technical_decisions.md#5-resampling).

### 4. Scale DN to reflectance

**Function**: `dn_to_reflectance(dn_array, baseline, offset, quantification,
clip, nodata_dn)`, in `preprocessing/reflectance.py`.

**In**: the raw integer band (DN) returned by stage 3, plus the scaling read in
stage 2.

**Out**: the same band as `float32`, with reflectance in `[0, 1]` and `NaN`
wherever the product had no data.

**The non-obvious decision**: `DN == 0` becomes `NaN` **before** scaling, not
after. Zero is the product's no-data value; scaling it with the -1000 offset
would give -0.1, which the clip would floor to 0.0: a perfectly valid and
perfectly fake number that contaminates means, percentiles and the contrast
stretch of every figure without leaving a trace.

### 5. Build the validity mask

**Function**: `build_cloud_mask(scl_band, classes_to_mask)`, in
`preprocessing/masking.py`, with `DEFAULT_INVALID_CLASSES = [0, 1, 2, 3, 6, 8,
9, 10, 11]`.

**In**: the SCL band already cropped and resampled with `nearest` (stage 3), and
the list of classes to discard.

**Out**: a boolean mask `(height, width)` where **`True` = valid pixel**. It is
the complement of a cloud mask, despite the function's name.

`scene_builder` combines it with a second criterion before storing it:

```python
mask_final = mask_scl & ~np.isnan(cube).any(axis=0)
```

The second term catches tile edges, where SCL may report "soil" while the band
carries no signal.

**The non-obvious decision**: the cube is **handed back unmasked**. Validity
travels separately, in `Scene.mask`, and applying it is the consumer's call. A
pixel turned into `NaN` cannot be recovered without re-reading the product,
whereas masking later is always possible; and there are legitimate consumers of
the full cube — global statistics, a method that needs the whole neighbourhood.
The explicit step is `apply_mask(cube, mask)`, which returns a copy with `NaN`
across all bands of the invalid pixels.

Which class is discarded and why:
[technical decisions §4](technical_decisions.md#4-validity-mask).

### 6. Hand back and serialise the `Scene`

**Function**: `build_scene_from_safe(root, band_names, aoi,
invalid_scl_classes, verbose)`, in `preprocessing/scene_builder.py`. This is
what chains stages 1 to 5.

**In**: the directory holding the `.SAFE`, the requested bands (by default the
12 in `BAND_ORDER`) and the AOI.

**Out**: a `Scene` with `cube` `(n_bands, height, width)` as `float32`,
`band_names`, the cropped AOI's `transform`, `crs`, `mask` and `meta`.

`meta` records where the cube came from: product, tile, sensing date, baseline,
offset, AOI window, native resolution per band, discarded SCL classes and the
AOI's SCL composition. **It is documentation, not configuration**: nothing in
the pipeline reads `meta` to decide what to do
([technical decisions §1.1](technical_decisions.md#11-scene--srcmineralmapioraster_iopy)).

`save_scene` / `load_scene` serialise it to a single `.npz` — the cube as
`float32`, the `transform` as its 6 coefficients, the CRS as WKT and `meta` as
JSON. JSON instead of pickle is what allows loading with `allow_pickle=False`:
opening a scene can never execute code.

### 7. Reference signature and visual comparison

**Functions**: `get_reference_spectrum(mineral, band_order)`, in
`spectral/endmembers.py`, and `plot_spectra(signatures, band_order, normalize)`,
in `visualization/spectra.py`.

**In**: the mineral name (`"kaolinite"`) and the consumer's band order —
typically `scene.band_names`.

**Out**: a 1D vector of length `len(band_order)`, aligned **positionally** with
it.

**The non-obvious decision**: the consumer dictates the ordering. The USGS
library has its own (13 bands, including B10) and the `Scene` has another (12,
without B10); forcing the conversion into one place, with the order stated
explicitly, is what stops SAM from comparing B11's reflectance against B12's
reference value and returning an impeccably computed, meaningless map. That
alignment is verified at three levels
([technical decisions §7](technical_decisions.md#alignment-verification-the-result)).

## How to run it

From the repository root, with the environment from the
[README](../../README.md) active:

| Command | What it does | What it leaves |
|---------|--------------|----------------|
| `python scripts/construir_scene.py` | Stages 1 to 6 over the default AOI, and prints the summary | `data/interim/scene.npz` |
| `python scripts/visualizar_rgb.py` | True-colour composite (B4/B3/B2) with a percentile stretch | `outputs/figures/scene_rgb.png` |
| `python scripts/visualizar_mascara.py` | Re-reads SCL over the `Scene` window and draws it next to `Scene.mask` | `outputs/figures/mascara_scl.png` |
| `python scripts/plot_kaolinite_signature.py` | Kaolinite reference signature, band by band | `outputs/figures/kaolinite_signature.png` |

`visualizar_rgb.py` and `visualizar_mascara.py` load `data/interim/scene.npz`
and, if it is missing, build the `Scene` from `data/raw/`.
`plot_kaolinite_signature.py` does not need the scene: the `.txt` in
`data/external/` is enough. It is also the only one still plotting on a band
index axis instead of using `plot_spectra`, which is what notebook 01 and the
`kaolinite_signature_vs_pixel.png` figure do.

`notebooks/01_explore_sentinel2_scene.ipynb` walks the same flow interactively
and closes with the alignment check between cube and reference signature.

## What is missing: stages 8 to 10, pending Tier 1

None of what follows is wired up. It is documented so that **what is missing**
is clear, not to suggest it exists.

**8. Detection algorithm.** `algorithms/sam.py` *is* implemented and tested:
`SAM.predict(cube, reference)` returns the spectral angle map and
`threshold(angle_map, max_angle)` binarises it. What does not exist is the
orchestrator that would run it over a `Scene`:
`pipeline.py::run_pipeline(config)` raises `NotImplementedError` and
`scripts/run_pipeline.py` calls it, so the README quickstart does not yet
produce a map. On top of that, the threshold set in
`configs/tamarugal_kaolinite.yaml` (`angle_threshold_rad: 0.1`) **would not
detect a single pixel** over the 256 × 256 px window of the AOI where it was
measured; the value is deliberately left in place, waiting for a calibration
criterion rather than another number picked by eye
([technical decisions §7](technical_decisions.md#the-config-threshold-would-detect-nothing)).

**9. Validation against geological mapping.** `validation/geology.py` (loading
SERNAGEOMIN polygons and rasterising ground truth) and `validation/metrics.py`
(confusion matrix, F1, IoU, ROC/AUC, kappa) are complete stubs: every function
raises `NotImplementedError`. No ground truth has been downloaded into
`data/external/`.

**10. Result visualisation.** `visualization/maps.py::plot_score_map()` is a
stub. What the module does implement is what preprocessing consumes:
`percentile_stretch`, `rgb_composite`, `scl_to_rgb` and `plot_scl_classes`.
Likewise `io/raster_io.py::write_geotiff()` and `read_scene()` remain
unimplemented, so there is still no way to export a score map to GeoTIFF.

**Consequently, the project reports no kaolinite detection.** What is verified
today is in the "Results" section of the [README](../../README.md#results).
