# Technical decisions

This document records the design decisions already made and implemented in the
repository, together with their rationale and what would break if they were
reversed. Each one points at the file and function where it lives.

The constraint driving most of what follows is that the project scales in
tiers — Tier 1 (Spectral Angle Mapper), Tier 2 (Random Forest), Tier 3
(spectral unmixing) — and the architecture must support all three without a
refactor.

## 1. Interface contracts

These are the three boundaries between subsystems. As long as they hold, any
subsystem can be rewritten internally without touching the others.

### 1.1 `Scene` — `src/mineralmap/io/raster_io.py`

The object produced by `preprocessing/` and consumed by `spectral/` and
`algorithms/`. It knows nothing about file formats — it is data in memory.

| Field        | Type         | Shape / contents |
|--------------|--------------|------------------|
| `cube`       | `np.ndarray` | `(n_bands, height, width)`, `float32`, reflectance in `[0, 1]` or `NaN` |
| `band_names` | `list[str]`  | Canonical names, aligned **positionally** with axis 0 of `cube` |
| `transform`  | `Affine`     | Georeferencing of the cropped AOI, not of the full tile |
| `crs`        | `CRS`        | Reference system (EPSG:32719 for this scene) |
| `mask`       | `np.ndarray` | `(height, width)`, `bool` |
| `meta`       | `dict`       | Provenance; defaults to `{}` |

Three non-negotiable conventions:

**`mask` is `True` where the pixel is usable.** It is the complement of a cloud
mask, not the cloud mask itself. The function that builds it is named
`build_cloud_mask` for historical reasons and its docstring flags the mismatch
loudly. Flipping the convention would break `apply_mask`,
`build_scene_from_safe` and their tests without raising anything: the pipeline
would simply analyse the clouds instead of the ground.

**`band_names` ordering is positional, not nominal.** `cube[i]` is band
`band_names[i]`. Nothing looks bands up by name inside the cube except the
visualisation layer. This is why `get_reference_spectrum` takes a `band_order`
and returns a vector aligned to it: the SAM dot product assumes that alignment
and has no way to verify it.

**`meta` is documentation, not configuration.** Nothing in the pipeline reads
`meta` to decide what to do. It records where the cube came from: `safe_name`,
`tile_id`, `sensing_date`, `processing_baseline`, `boa_offset`,
`quantification`, `aoi_window`, `bands_source` (band → native resolution),
`invalid_scl_classes`, `scl_summary` and `created_at`. It is serialised as JSON
inside the `.npz`, so `load_scene` never needs `allow_pickle=True` and opening a
scene can never execute code. An `.npz` written before `meta` existed loads with
`meta == {}` rather than failing.

### 1.2 `Detector` — `src/mineralmap/algorithms/base.py`

```python
class Detector(ABC):
    @abstractmethod
    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray: ...
```

Takes the `(n_bands, height, width)` cube and the `(n_bands,)` reference
signature; returns a 2D score map `(height, width)` where a higher value means
stronger evidence of the mineral.

**This is the project's scalability mechanism.** The pipeline does not know
which algorithm is running: it builds a `Detector` from the experiment YAML
(`algorithm.name`) and calls `predict`. Going from Tier 1 to Tier 2 means adding
a class under `algorithms/` and one line in a config — not rewriting the flow.
`SAM` (`algorithms/sam.py`) implements the contract today; `random_forest.py`
and `unmixing.py` are deliberate scaffolding that will implement it later.

The awkward consequence, accepted knowingly: the `predict(cube, reference)`
signature is shaped for methods that compare against a signature. A Random
Forest trained on labelled samples does not use `reference` the same way. That
will be resolved when it is implemented — most likely by ignoring the argument
or using it to seed the positive samples — but the signature stays, because
changing it would force a pipeline change, which is exactly what the contract
exists to prevent.

### 1.3 `get_reference_spectrum` — `src/mineralmap/spectral/endmembers.py`

```python
def get_reference_spectrum(mineral: str, band_order: list[str] = BAND_ORDER) -> np.ndarray
```

Returns a 1D vector of length `len(band_order)` holding the mineral's reference
reflectance, aligned positionally with `band_order`. It locates the USGS splib07
file registered in `ENDMEMBERS` under `data/external/`, drops B10 (which the
library provides but the L2A product does not) and reorders the remaining 12
values. Raises `KeyError` for an unregistered mineral.

The design point is that **the consumer dictates the ordering**. The USGS library
has its own order and `Scene` has another; forcing the conversion to happen here,
in one place and with the order stated explicitly, is what prevents a silent
misalignment between cube and signature.

## 2. Bands

### `BAND_ORDER` — 12 bands

`src/mineralmap/config.py`. The project's band contract:

```
B1, B2, B3, B4, B5, B6, B7, B8, B8A, B9, B11, B12
```

Canonical names carry **no leading zero**; the product's `.jp2` files use `B01`,
`B08`, and the translation lives in `BAND_TOKEN` (`io/raster_io.py`), generated
programmatically from `BAND_ORDER` so that adding a band to the contract does
not also require maintaining a hand-written dictionary.

**B10 is absent** (cirrus, ~1375 nm) because it does not exist in the L2A
product: Sen2Cor discards it during atmospheric correction, since it is only
useful for cirrus detection on the L1C product. Including it would make scene
construction fail with a `FileNotFoundError` looking for a file the product
never ships.

### `COMMON_BANDS` — 6 bands, no longer the default

The subset of natively-20 m bands used for the first `Scene`. It stopped being
the default when `Scene` moved to 12 bands: the Track A roadmap called for
"resample all bands to 20 m", and `BAND_ORDER` is the contract agreed in Week 0.
It survives as a documented subset and is still reachable from the CLI
(`--bands common`).

### `SAM_BANDS` — 9 bands, declared and not yet consumed

```
B2, B3, B4, B5, B6, B7, B8A, B11, B12
```

The subset the spectral detector will consume. Today it is **only declared** —
no module imports it. Declaring it ahead of use puts the decision in writing and
under test while the pipeline does not yet exist.

The three exclusions relative to `BAND_ORDER`, each for its own reason:

- **B1** (443 nm, coastal aerosol) exists to feed atmospheric correction. Its
  variance describes the state of the atmosphere, not the surface.
- **B9** (945 nm, water vapour absorption) has the same problem, and is also the
  only band with a 60 m native resolution — the least real information per pixel
  in the whole cube.
- **B8** (833 nm, wide) overlaps **B8A** (865 nm, narrow), which covers the same
  region with better spectral definition. Keeping both would give the near
  infrared double weight in the spectral angle, which sums over bands and does
  not discount redundancy.

**The `Scene` is still built with all 12 bands.** Subsetting later is always
possible; recovering a band that was never read off disk is not. The cost of the
three extra bands is memory, and memory is cheap next to re-reading the product.

## 3. Study area

| Parameter | Value |
|-----------|-------|
| Tile | `T19KDT` (Pampa del Tamarugal, Tarapacá Region, Chile) |
| Product | `S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE` |
| CRS | EPSG:32719 (UTM 19S) |
| AOI window | `col_off=1000, row_off=1000, width=2000, height=2000`, on the 20 m grid |
| Extent | 40 × 40 km |
| WGS84 bbox | `[-69.7673, -20.4377, -69.383, -20.075]` |

**The pixel window is authoritative; the bbox is informational.** The window
defines an exact, reproducible crop on the tile grid, whereas the bbox goes
through a reprojection and ends up rounded. When a bbox is handed to
`build_scene_from_safe` it is reprojected with `transform_bounds`, converted to
a window and rounded with `round_offsets().round_lengths()`. Both values coexist
in `configs/tamarugal_kaolinite.yaml` with that hierarchy annotated.

**The study area changed from the original plan.** The project originally
targeted the Chuquicamata district (Calama, Antofagasta Region); it moved to
Pampa del Tamarugal because of data availability. The `chuqui_kaolinite.yaml`
config became obsolete and was renamed to `tamarugal_kaolinite.yaml`. There is
exactly one valid version of this fact: any reference to Chuquicamata as the
active study area elsewhere in the repository is a leftover and should be fixed.

The scene is almost entirely clear: 99.9977 % valid pixels across the AOI,
99.92 % classified as bare soil. That is deliberate — absolute desert, no
vegetation and no cloud — because the goal is detecting a mineral signature at
the surface, and any cover masks it.

## 4. Validity mask

`src/mineralmap/preprocessing/masking.py`.

```python
DEFAULT_INVALID_CLASSES = [0, 1, 2, 3, 6, 8, 9, 10, 11]
```

Discarded: no data (0), saturated or defective (1), cast shadow (2), cloud
shadow (3), water (6), medium-probability cloud (8), high-probability cloud (9),
thin cirrus (10) and snow or ice (11).

Three classes are kept, each for its own reason:

- **5, bare soil** is the target itself. It is where the mineral signature
  reaches the sensor unobstructed.
- **4, vegetation** is not an invalid pixel, merely an uninformative one for a
  mineral. Filtering it is the algorithm's call, not preprocessing's:
  preprocessing should not discard data a later method might want — a Random
  Forest, for instance, learns from the contrast.
- **7, unclassified** is Sen2Cor's "don't know" bucket. Discarding it would mean
  trusting its classification more than is warranted over arid terrain, where it
  is frequently wrong.

Water is discarded: its spectral signature does not compete with a mineral's and
contributes only false positives.

**The mask is not applied to the cube.** `build_scene_from_safe` hands back the
raw cube and validity separately in `Scene.mask`. Masking is the consumer's
decision, not the constructor's: one algorithm may want global statistics,
another may need the full neighbourhood, and once a pixel has become `NaN` there
is no way back without re-reading the product. The explicit helper is
`apply_mask(cube, mask)`, which returns a copy with `NaN` across all bands of the
invalid pixels and validates the shapes.

The final mask combines two criteria: `mask_scl & ~np.isnan(cube).any(axis=0)`.
The second term catches tile edges, where SCL may report "soil" while the band
carries no signal.

## 5. Resampling

`src/mineralmap/preprocessing/resampling.py`.

**Resampling happens at read time, not on an assembled `Scene`.**
`read_band_on_grid` translates the AOI bounds into a window on each band's native
grid and asks GDAL to deliver it already shaped to the target grid. The `Scene`
is born homogeneous at 20 m and a cube with mixed-resolution bands never exists.
Resampling afterwards would mean interpolating twice, and every interpolation
degrades radiometry.

`resample_to_common_grid` remains a stub reserved for Tier 2, when `Scene`
objects from different grids must be combined and the problem can no longer be
solved at read time.

`resampling_for(src_res_m, target_res_m, categorical)` picks the method:

| Case | Method | Rationale | Band in this scene |
|------|--------|-----------|--------------------|
| Categorical | `nearest` | Averaging labels produces classes that do not exist | SCL (R20m) |
| Downsample 10 → 20 m | `average` | Averaging the 4 contributing pixels preserves radiometry better than picking one | B8 (R10m) |
| Upsample 60 → 20 m | `bilinear` | Interpolation smooths the block instead of replicating it in steps | B9 (R60m) |
| Same resolution | `nearest` | Identity; interpolating for its own sake only adds error | B1–B7, B8A, B11, B12 |

The categorical case is the one that matters. The average of "water" and "cloud"
is not "vegetation", but that is precisely what `average` over labels returns.
It is a classic and expensive mistake because it does not fail — it hands back a
plausible, wrong mask.

**The premise that makes all of this valid**: within a Sentinel-2 L2A tile every
band shares the same CRS and tile origin, and their resolutions are exact
multiples of one another. That is why cropping by coordinates and rescaling is
enough, with no `warp` involved. What would break it: combining different tiles,
different dates, or another sensor — those require real reprojection. So the
premise cannot be violated silently, `read_band_on_grid` accepts an
`expected_crs` and raises `ValueError` on a mismatch: cropping by coordinates in
the wrong CRS does not error, it produces garbage.

## 6. Reflectance

`src/mineralmap/preprocessing/reflectance.py`.

```
reflectance = (DN + offset) / quantification
```

For this scene: `offset = -1000`, `quantification = 10000`, baseline `05.11`.
All three are **read from `MTD_MSIL2A.xml`** (`read_l2a_scaling`) rather than
hard-coded: they depend on which version ESA used to process the product, and a
reprocessed scene can change them with nothing else changing. The parser ignores
XML namespaces by comparing only the last segment of each tag, because the PSD
namespace changes between product versions and anchoring to it breaks parsing
without warning. If the XML is missing, it falls back to
`("04.00", -1000.0, 10000.0)` with an explicit `warnings.warn`.

**Why the offset exists.** Up to baseline 03.xx the product stored
`reflectance × 10000`. From baseline 04.00 onwards, Sen2Cor encodes reflectance
with a shift: it stores `reflectance × 10000 + 1000`. The shift allows slightly
negative reflectances — a normal outcome of atmospheric correction over very
dark surfaces — to be represented without switching to signed integers. In the
XML the value appears as `BOA_ADD_OFFSET = -1000`: a negative addend, equivalent
to subtracting 1000. Applying the old formula to a modern product introduces a
systematic +0.1 reflectance error, which over arid soil is roughly 40 % of the
true value.

**Why `DN == 0` becomes `NaN`.** Zero is the product's no-data value. Scaling it
would yield `-0.1`, which the clip would floor to `0.0`: a perfectly valid and
perfectly fake number. It contaminates every downstream statistic — means,
percentiles, the percentile stretch used for figures — leaving no trace. Hence
no-data is identified on the raw DNs, before scaling.

**What the clip buys and costs.** With `clip=True` (the default) the result is
bounded to `[0, 1]`. The gain: reflectances outside that range are artefacts of
the atmospheric correction rather than measurements, and carrying them pollutes
any later normalisation. The cost: the information about *how far* out of range a
pixel was is lost, and that is a useful diagnostic for areas where Sen2Cor
struggled. In the current AOI the clip engages on the brightest pixels (the
cube's maximum is exactly `1.0`). `np.clip` propagates `NaN`, so no-data survives
the clamp; there is an explicit test for this, because it is exactly the kind of
detail an alternative implementation would break silently.
