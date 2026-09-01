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
| 8 | Detection algorithm | `algorithms/sam.py`, `pipeline.py` | Implemented |
| 9 | Validation against geological mapping | `validation/`, `scripts/evaluate.py` | Implemented |
| 10 | Result visualisation and export | `visualization/maps.py`, `io/raster_io.py` | Implemented |

Stages 1 to 6 are the preprocessing that Week 2 closed, and a single function
chains them: `build_scene_from_safe()`. Stages 7, 8 and 10 are chained by
`run_pipeline(config)`, which Week 3 closed: from the experiment's YAML to the
GeoTIFF and the heatmap, with no manual steps. Stage 9 closed in two steps: the
ground-truth layer in Week 4 and the metrics in Week 6.

**The only unimplemented stage is 0**, automatic scene acquisition, which stays
manual on purpose: it is Tier 2 and blocks nothing as long as the `.SAFE`
product is downloaded.

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
(`col_off=2700, row_off=650, 2000×2000` px at 20 m, i.e. 40 × 40 km); a
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
the pipeline takes from `meta` a parameter that decides what gets computed. It
is read in two places, and neither contradicts that: `_cache_coincide` compares
`meta["aoi_window"]` against the config's window, where all `meta` can do is
**veto** the cache — it never supplies the AOI, which always comes from the
config — and `_guardar_heatmap` reads `tile_id` and `sensing_date` for the
figure title, a cosmetic use that enters no computation
([technical decisions §1.1](technical_decisions.md#11-scene--srcmineralmapioraster_iopy)).

`save_scene` / `load_scene` serialise it to a single `.npz` — the cube as
`float32`, the `transform` as its 6 coefficients, the CRS as WKT and `meta` as
JSON. JSON instead of pickle is what allows loading with `allow_pickle=False`:
opening a scene can never execute code.

**The `.npz` is not reproducible byte for byte.** `meta` includes `created_at`,
so two rebuilds of the same AOI give files with different hashes even when the
cube is identical. This does not affect the E1 reproducibility criterion: what
has to come out identical is the `.tif`, and it does. It is noted so that nobody
uses the `.npz` hash as a content identity — it is a cache, not a deliverable,
and it is not versioned. `created_at` is kept deliberately: the cube's
provenance is worth more than a hash nobody compares.

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

## The implemented flow: from `Config` to map

```
configs/cerro_colorado_kaolinite.yaml
   |
   |-- load_config(path) ................... Config (scene, aoi, mineral, algorithm, output)
   |
   v
run_pipeline(config)
   |
   |-- _normalizar_root_escena(scene.path) . directory to search for the .SAFE
   |-- _resolver_aoi(aoi) .................. Window from aoi.window_px
   |
   |   data/interim/scene.npz  --(if window and bands match)-->  Scene
   |          ^                                                    |
   |          +--- otherwise: build_scene_from_safe(root, bands, aoi) --+
   |
   v
apply_mask(scene.cube, scene.mask)          NaN on invalid pixels
   |
   +--> cube[SAM_BANDS indices] ............. 9 bands, not 12
   |
   |    get_reference_spectrum("kaolinite", band_order=SAM_BANDS)
   |                     |
   v                     v
_crear_detector(algorithm.name) -> Detector.predict(cube, reference)
   |
   v
angle map (height, width), NaN where ~scene.mask
   |
   +-- write_geotiff ---> outputs/maps/kaolinite_sam_angle.tif
   +-- plot_score_map --> outputs/figures/kaolinite_sam_angle.png
   +-- dict of paths and statistics (what the CLI prints)
```

### 8. Detection algorithm and its orchestrator

**Functions**: `SAM.predict(cube, reference)` and `threshold(angle_map,
max_angle)` in `algorithms/sam.py`; `run_pipeline(config)` in `pipeline.py`.

**In**: a `Config` loaded with `load_config`. From it come the scene
(`scene.path`, `scene.bands`), the AOI (`aoi.window_px`), the target mineral
(`mineral.target`), the algorithm (`algorithm.name`) and the output paths
(`output`).

**Out**: the spectral angle map in radians `(height, width)` with `NaN` on
invalid pixels, plus a `dict` of the paths written and the map's statistics.
The function returns data; printing is the CLI's job.

**There are four non-obvious decisions**:

1. **The detector is instantiated from a registry**, not from an `if`.
   `DETECTORS` maps `algorithm.name` to the class, and the rest of the flow
   never names SAM. Adding Random Forest is one class in `algorithms/` and one
   entry in that dict
   ([technical decisions §1.2](technical_decisions.md#12-detector--srcmineralmapalgorithmsbasepy)).
2. **`scene.path` is normalised before the product is located.** The configs
   point at the `.SAFE` folder itself, but `find_safe_dir(root)` looks for
   `.SAFE` folders *under* `root`: handing it the product path finds nothing
   and aborts with a `FileNotFoundError` blaming the scene for not being
   downloaded when it is right there. The normalisation lives in the pipeline
   so that `find_safe_dir`, which already has tests, keeps its contract.
3. **The cache is verified before it is used.** `data/interim/scene.npz` is
   reused only if its window and bands are the ones the config asks for. A
   cache used blindly is the project's worst failure mode: the pipeline runs to
   completion, writes a valid GeoTIFF and the map belongs to a different AOI.
   Anything that cannot be verified counts as a mismatch and the product is
   re-read — three minutes of reading beat a wrong map. `--no-cache` skips it.
4. **`aoi.window_px` beats `aoi.bbox`.** The window is expressed on the tile's
   20 m grid, which is the exact definition of the AOI; the WGS84 bbox is its
   rounded equivalent. If the bbox won, the crop would shift by a few pixels
   with nothing to report it. This stage is `window_px`'s first consumer:
   until Week 3 nothing read it.

**The detector consumes 9 bands, not 12.** The `Scene` is still born with the
12 of `BAND_ORDER` and the pipeline subsets it to `SAM_BANDS` **by index**,
with the same ordering it uses to request the signature from
`get_reference_spectrum`
([technical decisions §2](technical_decisions.md#sam_bands--9-bands-consumed-by-the-detector-since-week-3)).

**Zero detections is a result, not an error.** The pipeline reports how many
pixels fell below `angle_threshold_rad` alongside a threshold sweep (0.05 to
0.20 rad) and writes the angle map regardless: the map is the deliverable, and
the threshold is waiting on a calibration criterion. Without that sweep, an
empty result is indistinguishable from a computation error.

### 10. Result visualisation and export

**Functions**: `write_geotiff(path, array, scene, band_descriptions)` in
`io/raster_io.py` and `plot_score_map(score_map, scene, title, p_low, p_high)`
in `visualization/maps.py`.

**In**: the 2D map returned by stage 8 and the `Scene` it came from.

**Out**: `outputs/maps/kaolinite_sam_angle.tif` (`float32` GeoTIFF, EPSG:32719,
`deflate`, `tiled`, `NaN` as nodata and the band described) and
`outputs/figures/kaolinite_sam_angle.png` (map + histogram).

**There are four non-obvious decisions**:

1. **`write_geotiff` validates the spatial shape against the `Scene`.** Writing
   a map computed over a different window yields a flawless GeoTIFF that opens
   in any GIS and lands on the wrong ground. It is the function's only failure
   mode that goes unnoticed, so it is a `ValueError` carrying both shapes.
2. **No tags of our own are written** (date, user, source path): the file comes
   out byte-for-byte identical across two consecutive runs, which is what makes
   reproducibility checkable by comparing hashes. Provenance already travels in
   `Scene.meta`.
3. **Nodata is `NaN`, not `0`.** A 0 rad angle is a perfect match against the
   signature: using it as a sentinel would turn the masked pixels into the
   map's strongest detections.
4. **The figure is two panels.** The map says *where*; the histogram says
   *whether there is anything to look at*, and what to read in it is **whether
   the end you care about is overpopulated relative to a bell**, not which way
   the long tail falls. Over this AOI the long tail runs towards **high**
   angles — skewness is +0.76 — and the histogram still carries the spectral
   coherence: 0.1 rad sits 5.2 standard deviations below the mean, where a
   Gaussian would give 0.43 pixels in 4 million, and there are 62. The map
   alone cannot tell such an excess from noise. The colour scale is clipped to
   the 2–98 percentiles rather than the full `[0, π]` range — the full AOI's
   angles span 0.07 to 0.70 rad — the percentiles are computed with `np.nanpercentile`
   (a single `NaN` under `np.percentile` flattens the panel without raising
   anything), and the axes are in CRS coordinates derived from
   `scene.transform`, not pixel indices.

## How to run it

From the repository root, with the environment from the
[README](../../README.md) active:

| Command | What it does | What it leaves |
|---------|--------------|----------------|
| `python scripts/construir_scene.py` | Stages 1 to 6 over the default AOI, and prints the summary | `data/interim/scene.npz` |
| `python scripts/visualizar_rgb.py` | True-colour composite (B4/B3/B2) with a percentile stretch | `outputs/figures/scene_rgb.png` |
| `python scripts/visualizar_mascara.py` | Re-reads SCL over the `Scene` window and draws it next to `Scene.mask` | `outputs/figures/mascara_scl.png` |
| `python scripts/plot_kaolinite_signature.py` | Kaolinite reference signature, band by band | `outputs/figures/kaolinite_signature.png` |
| `python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml` | Stages 7, 8 and 10 end to end: resolves the `Scene`, runs the detector and prints the summary | `outputs/maps/kaolinite_sam_angle.tif` and `outputs/figures/kaolinite_sam_angle.png` |
| `python scripts/verificar_cifras.py` | Recomputes from the `.tif` the figures the README and section 7 publish, compares them against what those files say, and exits 1 if any disagrees | Nothing: it only reads and prints |

`visualizar_rgb.py` and `visualizar_mascara.py` load `data/interim/scene.npz`
and, if it is missing, build the `Scene` from `data/raw/`.
`plot_kaolinite_signature.py` does not need the scene: the `.txt` in
`data/external/` is enough. It is also the only one still plotting on a band
index axis instead of using `plot_spectra`, which is what notebook 01 and the
`kaolinite_signature_vs_pixel.png` figure do.

`notebooks/01_explore_sentinel2_scene.ipynb` walks the same flow interactively
and closes with the alignment check between cube and reference signature.

## Stage 9: validation, complete

### The ground-truth layer (Week 4, Track A)

`validation/geology.py` is implemented. The full path is:

```
scripts/descargar_geologia.py
   |
   |-- Chile_Geology FeatureServer, layers 439 and 437, paged via resultOffset
   v
data/external/geologia/{pozo_almonte,mamina}.geojson   (EPSG:32719, versioned)
   |
   |-- load_geology_polygons(path) ......... GeoDataFrame; demands CRS, polygons
   |-- clasificar_unidades(gdf, config) .... `clase` column, per the YAML
   |-- rasterize_ground_truth(gdf, scene) .. reprojects and burns to the grid
   v
outputs/maps/ground_truth.tif   (2000x2000, same crs and transform as the angle
                                 map; `write_geotiff` checks it)
```

`build_ground_truth(config_path, scene)` chains it and also returns a
traceability dict (files used, polygons and pixels per class, AOI fraction,
unclassified units). `scripts/construir_verdad_terreno.py` is the CLI that runs
and prints it.

The layer carries **three** values: `1` positive, `0` negative and `255`
ambiguous (unclassified unit, or pixel outside every polygon). Why the third
class exists is in [technical_decisions.md](technical_decisions.md), section 9.

Which unit counts as positive is **not in the code**: it is declared in
`configs/verdad_terreno_cerro_colorado.yaml`, because it is a geological judgement
and not a fact from the map. With that YAML left empty the pipeline still runs
and produces a 100 % ambiguous layer; today it is filled in, and the layer
splits into 50,773 positive pixels (1.27 % of the AOI), 192,444 negative
(4.81 %) and 3,756,783 ambiguous (93.92 %).

Figure F5, `outputs/figures/overlay_deteccion_geologia.png`, overlays the angle
map and the polygons; `visualization/maps.py::plot_overlay_geologia` draws it.

**One thing to know when consuming the .tif**: `write_geotiff` always writes
float32 with `nodata=NaN`, so `ground_truth.tif` carries `1.0`, `0.0` and
`255.0` as float32, not uint8. All three are exact in float32, but a reader has
to cast before comparing for equality.

### The metrics (Week 6, Track B)

`validation/metrics.py` and `scripts/evaluate.py` are implemented. The path is:

```
outputs/maps/kaolinite_sam_angle.tif  +  outputs/maps/ground_truth.tif
   |
   |-- evaluar_desde_rasters(...) ....... reads both and ABORTS if crs,
   |                                      transform or shape disagree
   |-- preparar_pares(...) .............. THE ONLY filter: drops ambiguous,
   |                                      score NaN and Scene-mask pixels
   |-- confusion_matrix / precision / recall / f1 / iou / cohen_kappa / roc_auc
   |-- curva_roc(...) .................. full ROC + Youden and maximum-F1
   v                                      thresholds
printed table  +  --out JSON  +  --figura outputs/figures/roc_kaolinite_sam.png
```

The five metrics are pure NumPy, with no `scikit-learn` in production, and
`preparar_pares` is **the single place** that decides which pixel enters the
computation: keeping that filter in one location is what stops one metric from
excluding the `255` pixels while another does not. The AUC requires the score
direction as a mandatory argument (`higher_is_better`), because SAM's angle runs
the other way and measuring it with the sign flipped returns `1 - AUC` without
raising anything.

`scripts/evaluate.py` is the CLI:

```bash
python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif \
    outputs/maps/ground_truth.tif --figura
```

It prints how many pixels entered and how many were discarded per cause, the
confusion matrix, the six metrics and the two calibration thresholds. The
threshold and the direction come from the experiment config, not from constants
in the script.

**This is what allowed — and now forbids — calling the stage 8 map a "kaolinite
detection".** Measured: over 242,967 evaluable pixels F1, IoU and kappa are all
0, and the **ROC AUC is 0.2403**, below the 0.5 of chance. The detector does not
merely fail to separate the classes: it separates them the wrong way round. The
figures and their reading are in the "Results" section of the
[README](../../README.md#results) and in
[technical_decisions.md](technical_decisions.md), sections 7 and 11.

`io/raster_io.py::read_scene()` also remains unimplemented. It is the
counterpart of reading a multi-band `Scene` back from GeoTIFF and it blocks
nothing: the `Scene` is serialised to `.npz` with `save_scene`/`load_scene`,
and `write_geotiff` exists to export results, not to read them back.
