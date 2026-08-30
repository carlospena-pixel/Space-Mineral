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

**`meta` is documentation, not configuration.** The exact invariant is that
**nothing in the pipeline takes from `meta` a parameter that decides what gets
computed**: the AOI, the bands and the algorithm come from the config on every
path. `meta` is read in two places and neither contradicts that:

- `_cache_coincide` compares `meta["aoi_window"]` against the config's window.
  All `meta` can do there is **veto** the cache; if it is missing or does not
  match, the `Scene` is rebuilt from the `.SAFE`. It never supplies the AOI, it
  can only reject a cached one.
- `_guardar_heatmap` reads `tile_id` and `sensing_date` for the **figure
  title**. That use is cosmetic: it enters no computation, and an empty `meta`
  produces the same figure with a shorter title.

It records where the cube came from: `safe_name`,
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

### `BAND_WAVELENGTHS_NM` and `BAND_FWHM_NM` — wavelength as project data

`src/mineralmap/config.py`. Central wavelength and bandwidth (FWHM) for every
band, in nanometres, with **one table per platform** and
`DEFAULT_PLATFORM = "S2B"`, the platform that acquired this project's scene. The
`band_wavelengths(band_order, platform)` helper returns them aligned
positionally with the requested `band_order`, under the same contract as
`get_reference_spectrum`: the consumer dictates the ordering.

**Why there are two tables.** S2A and S2B are two satellites carrying two
physical copies of the MSI instrument, and their filters did not come out of the
factory identical. The largest divergence lands on exactly the band this project
cares about: B12 is centred at 2202.4 nm on S2A and at 2185.7 nm on S2B, 16.7 nm
apart. B12 is the band that samples kaolinite's Al–OH doublet (2160/2200 nm),
where reflectance changes rapidly with wavelength. Using the S2A table on an S2B
scene raises nothing: it shifts the band centre into the absorption feature and
returns a plot and an alignment check that look right and are wrong.

**B10 is included** even though `BAND_ORDER` excludes it. The L2A product does
not ship it, but the USGS library file does, and validating the alignment of the
reference signature needs to know where it falls.

The values are verified against SentiWiki (Copernicus), "S2 Mission", table 3,
derived from ESA's spectral response functions (COPE-GSEG-EOPG-TN-15-0007). The
central wavelengths match the ones circulating in the project; some FWHM values
do not (S2A's B8 appears as 106 nm in derived spreadsheets and as 118 nm in the
source). The cited source wins. The discrepancy affects nothing implemented
today: FWHM is declared pending `spectral/srf.py` and no module consumes it.

### `SAM_BANDS` — 9 bands, consumed by the detector since Week 3

```
B2, B3, B4, B5, B6, B7, B8A, B11, B12
```

The subset the spectral detector consumes. It sat declared without consumers
through Week 2 — the decision was written down and put under test before the
pipeline existed — and since Week 3 `run_pipeline` consumes it, subsetting the
cube and requesting the reference signature over these nine bands.

**Who imports it today**: `algorithms/sam.py`, where `SAM` declares it as its
`bands` attribute. The pipeline no longer imports it: it asks the detector which
bands it wants instead of trimming to `SAM_BANDS` unconditionally (see
[section 8](#8-the-sam-detector)).

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
| Tile | `T19KDT` (Cerro Colorado district, Tarapacá Precordillera, Chile) |
| Product | `S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE` |
| CRS | EPSG:32719 (UTM 19S) |
| AOI window | `col_off=2700, row_off=650, width=2000, height=2000`, on the 20 m grid |
| Extent | 40 × 40 km, E 453,960–493,960 / N 7,747,040–7,787,040 |
| WGS84 bbox | `[-69.4412, -20.3748, -69.0577, -20.0128]` |

**The pixel window is authoritative; the bbox is informational.** The window
defines an exact, reproducible crop on the tile grid, whereas the bbox goes
through a reprojection and ends up rounded. When a bbox is handed to
`build_scene_from_safe` it is reprojected with `transform_bounds`, converted to
a window and rounded with `round_offsets().round_lengths()`. Both values coexist
in `configs/cerro_colorado_kaolinite.yaml` with that hierarchy annotated.

**The study area changed twice.** The project originally targeted the
Chuquicamata district (Calama, Antofagasta Region); it moved to Pampa del
Tamarugal in Week 2 because of data availability, and in Week 5 it shifted
northeast to the Cerro Colorado district, because the pampa held no mapped
alteration to validate against (section 10). The config was successively named
`chuqui_kaolinite.yaml`, `tamarugal_kaolinite.yaml` and today
`cerro_colorado_kaolinite.yaml`. There is exactly one valid version of this
fact: any reference to Chuquicamata or Tamarugal as the active study area
elsewhere in the repository is a leftover and should be fixed.

The scene is still almost entirely clear: 99.8484 % valid pixels across the AOI,
99.8085 % classified as bare soil. That is deliberate — absolute desert, no
vegetation and no cloud — because the goal is detecting a mineral signature at
the surface, and any cover masks it. What gets discarded is almost all
topographic shadow (0.1505 %), the price of reaching into the Precordillera: the
previous window, over the flat pampa, discarded 92 pixels and this one discards
6,064. Still negligible against 4 million.

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

## 7. Comparing signatures

`src/mineralmap/visualization/spectra.py`.

`plot_spectra` is the only way a human can see whether the cube and the
reference signature are talking about the same band. Three decisions, each one
because the alternative produces a plot that looks right and misleads.

**The x axis is wavelength, not band index.** The index lies about distances:
B8A (864 nm) and B11 (1610 nm) are 745 nm apart, B5 (704) and B6 (739) are 35 nm
apart, yet on an index axis both steps measure the same. With the index, the
slope of any segment means nothing — and slope is exactly what you read to
recognise an absorption feature.

**The default normalisation is L2.** SAM compares directions, not magnitudes: it
is albedo-invariant by construction. Plotting at unit norm plots exactly what
the algorithm sees. Without normalising, the laboratory kaolinite signature
(AREF reflectance from the USGS library) and a real scene pixel (surface
reflectance) sit apart by a large factor — of order 2 to 4 depending on the
pixel — and the plot suggests a misalignment that does not exist. `NaN`s
propagate rather than becoming zero: a `NaN` means "this band was not measured",
whereas a zero means "this band measured zero reflectance", which is a different
fact and also moves the normalisation factor.

**There is an explicit gap where the sensor did not sample.** Between two
consecutive bands of `band_order` that are not neighbours on the sensor, the
line breaks. The concrete case is B9 (945 nm) and B11 (1610 nm): B10 does not
exist in the L2A product, so joining them with a continuous line draws an
interpolation across 665 nm with not a single measurement behind it.

### Alignment verification: the result

This is the Week 2 Track B deliverable, and it closed at three levels:

1. **Against ESA's table, in a test that runs without data.** `BAND_ORDER` is in
   increasing wavelength order, and the wavelength table is exactly `BAND_ORDER`
   plus B10, checked in both directions (`tests/test_config.py`).
   `validate_raw_band_order()` extends the same check to the 13 positions of the
   USGS file (`tests/test_endmembers.py`).
2. **Against the real scene**, in `tests/test_scene_builder.py`: the signature
   requested with `band_order=scene.band_names` carries as many values as the
   cube has bands, and subsetting the cube by index and requesting the signature
   by name reach the same band. Those are two different paths to the same band
   and nothing forces them to agree; if they diverged, SAM would compare B11's
   reflectance against B12's reference value and return an impeccably computed,
   meaningless map.
3. **Visually**, in `notebooks/01_explore_sentinel2_scene.ipynb`: an
   `idx | band | λ | ref_USGS | pixel` table followed by `assert`s, plus the
   figure `outputs/figures/kaolinite_signature_vs_pixel.png`.

**What is still missing to close it fully.** The ordering of `_RAW_BAND_ORDER` —
which band each position of the splib07 file is — remains anchored to physical
evidence rather than to the source: position 10 shows an isolated dip that can
only be the ~1400 nm OH overtone sampled by B10. The wavelength file from the
`ASCIIdata_splib07*_rsSentinel2` package is not in `data/external/`; until it
is, the test that consumes it stays under `skipif`. The same applies to
`USGS_RESAMPLING_PLATFORM = "S2A"`, which is declared but unverified.

### The config threshold is still uncalibrated

**Full AOI, 2000×2000 px** (3,993,936 valid pixels out of 4,000,000, i.e.
99.8484 %). It comes from the summary printed by
`python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml`:

| bands | min | p1 | median | max |
|-------|-----|----|--------|-----|
| `SAM_BANDS` (9) | 0.0662 | 0.2004 | 0.2795 | 0.6859 |

| threshold (rad) | pixels | % of valid AOI |
|-----------------|--------|----------------|
| 0.05 | 0 | 0.000 % |
| 0.08 | 28 | 0.001 % |
| 0.10 | **131** | 0.003 % |
| 0.15 | 1,482 | 0.037 % |
| 0.20 | 38,672 | 0.968 % |

The table has **only the 9-band row**: the pipeline runs `SAM_BANDS` and that is
all there is measured at this scale. The experiment was not repeated with
`BAND_ORDER` over the 4 million pixels, so that row does not exist and is not
estimated.

These figures belong to the Cerro Colorado window. Those of the previous AOI,
over the Pampa del Tamarugal, are in section 10 and in `CHANGELOG.md`, which is
where the change is narrated; they are not kept here so that this document
carries a single set of current numbers.

#### What the 131 pixels are: still not a detection

What follows is evidence in favour, and it is not enough. **The direction of an
absorption feature does not identify a mineral**: without checking against
ground truth there is no way to separate kaolinite from any other surface that
descends between B11 and B12.

The 131 pixels below 0.1 rad **do reproduce the Al–OH absorption in direction**:

| | the 131 | background (3,993,805 valid) | USGS KGa-1 signature |
|---|---|---|---|
| B12/B11 ratio (median) | **0.663** | 1.000 | 0.507 |
| with ratio < 1 | **131 of 131** | 50 % | — |
| mean reflectance, 9 bands | 0.278 | 0.207 | — |

The 131 descend from B11 to B12 and none touches the AOI edge — the closest is
248 px away — so they are not crop artefacts. They cluster into 20 connected
components under 8-neighbour connectivity, the largest of 79 pixels: they are
patches, not single-pixel noise. Nor are they isolated in their surroundings:
**the median of the 5 × 5 neighbourhood** is 0.1020 rad against 0.2795 for the
scene, and in 123 of the 131 that neighbourhood also stays below 0.15. With the
mean of the same neighbourhood it gives 0.1143 and 121 of 131; the statistic is
named because the two figures differ. The drop is shallower than the laboratory
signature's (0.663 against 0.507), which is what one expects of a 20 m pixel
where the mineral, if present, comes mixed with everything else in 400 m².

#### Where they fall: the figure that changes the reading

Since Week 5 the AOI includes mapped alteration, so the question that could not
even be stated before can now be counted:

| ground-truth class | AOI pixels | detections at 0.1 rad |
|---|---|---|
| positive (mapped alteration) | 50,773 (1.27 %) | **0** |
| negative (non-candidate) | 192,444 (4.81 %) | **0** |
| ambiguous (unclassified) | 3,756,783 (93.92 %) | **131** |

**130 of the 131 fall on a single unit**: `Depositos antropicos, botaderos de
mina`, the waste dumps of the Cerro Colorado mine, 16.79 km² and 1.05 % of the
AOI. The remaining one falls on a conglomeratic facies of the Altos de Pica
Formation.

That explains all three figures above at once: the connected patches, the mean
reflectance higher than the background (0.278 against 0.207) and the uniformly
sub-unity B12/B11 ratio are what one expects from crushed, freshly exposed rock
without the desert's crust and varnish. SAM is finding something real and
spatially coherent — 130 hits inside 1 % of the area — but it is disturbed
material, not *in situ* geology.

**Within the units declared positive the minimum angle is 0.1541 rad**, well
above the threshold: not a single mapped-alteration pixel resembles kaolinite at
this scale. That is the result to be able to explain, and the likeliest
explanation is that the desert's natural surface is coated by crust and varnish
that mask the signature, while mine material exposes it.

#### The conclusion is unchanged

`configs/cerro_colorado_kaolinite.yaml` sets `angle_threshold_rad: 0.1`. **That
value still has no calibration criterion**, and it is deliberately left
untouched here: it has to be replaced with a criterion, not with another number
picked by eye. Calibrating it requires the ROC curve, which is
`validation/metrics.py` work.

**131 pixels out of 3,993,936 are not a kaolinite detection.** The spectral
angle measures resemblance to a laboratory signature, not the presence of a
mineral: any surface that looks similar across 9 bands scores just as low. Now,
in addition, it is known *where* they fall, and the place is not the one E3 asks
for.

## 8. The SAM detector

`src/mineralmap/algorithms/sam.py`.

### The formula and its source

For a pixel `x` and the reference signature `r`, both vectors of `n_bands`
components:

```
θ(x, r) = arccos( (x · r) / (‖x‖ · ‖r‖) )
```

**Checked term by term against the project's document 05**, which is the source
of the specification:

| Aspect | Document 05 | Implemented |
|--------|-------------|-------------|
| Prior normalisation of the vectors | None; normalisation lives in the denominator | Same |
| Output unit | Radians | Radians (`np.arccos`) |
| Definition of the score | The angle itself ("small angle = high similarity") | The angle itself |
| `clip(-1, 1)` before `arccos` | Prescribed, to avoid `NaN` from numerical error | Present |
| Vectorisation | `einsum`/broadcasting, no per-pixel loops | `einsum` |
| Bands in the sum | 12 | `n_bands`, and the pipeline passes 9 |

The only divergence is the last one, and it is **deliberate**: document 05 was
written when the band contract was `BAND_ORDER`, and the project later decided
the detector would consume `SAM_BANDS` (section 2), with the measurement in
section 7 showing that the trim does not change the angle distribution. The
implementation fixes no band count: it validates that cube and signature agree
with each other, which is the property that actually matters.

**Consequence for the score direction.** Document 05 defines the score as the
angle, so lower means more similar. That puts `SAM`, the maps' `viridis_r`, the
configs' `angle_threshold_rad` and the `<=` in `threshold()` all on the same
side. See the debt at the end of this section.

### What it validates now, and what it raises

Previously `predict` only failed from inside `np.einsum`, with a message about
operand dimensions that mentions neither bands nor signatures. Now:

| Input | Reaction | Why it cannot pass silently |
|-------|----------|------------------------------|
| `cube` and `reference` with different band counts | `ValueError` naming **both lengths** | This is `BAND_ORDER` (12) crossed with `SAM_BANDS` (9). The pipeline makes it an everyday mistake |
| `cube` that is not 3D | `ValueError` with the shape received | A 2D cube is a signature, not a scene |
| `reference` that is not 1D | `ValueError` | A `(n, 1)` signature broadcasts and returns a map of the wrong shape with plausible values |
| `reference` with `NaN` or `inf` | `ValueError` with the positions | It turns the whole map into `NaN`, and an all-`NaN` map is indistinguishable from a fully masked scene |
| `reference` with zero norm | `ValueError` | There is no direction to measure an angle against. Same criterion as `normalize_signature` (section 7) |

**What it deliberately does NOT validate: `NaN` in the cube.** A cube with `NaN`
is the detector's normal input, not a pathological case: the pipeline hands it
the cube already masked with `apply_mask` (section 4). A `NaN` pixel returns
`NaN` and does not contaminate its neighbours, and a test pins that promise
down. Any validation rejecting a cube with `NaN` breaks the whole pipeline.

The `predict(cube, reference)` signature **did not change** and no `mask`
parameter was added, convenient as that would be: it is the scalability
mechanism of section 1.2, and masking is the consumer's job.

### Two behaviours that existed without being written down

- **Zero-norm pixel** (all bands exactly 0) → `NaN`. A null vector has no
  direction, so the angle against it is neither 0 nor π/2: it is undefined.
  Returning 0 would declare it a perfect match and paint it as the strongest
  detection on the map. `NaN` removes it by the same path as a masked pixel.
- **`threshold()` discards `NaN`**, which is correct, but that follows from
  IEEE-754 semantics — every comparison against `NaN` is false — and not from
  code written for it. It is recorded because a reimplementation that "cleaned"
  the `NaN` before comparing, say with `np.nan_to_num`, would turn them into
  `0.0` and therefore into the strongest detections on the map.

### Precision: the accumulator is `float64`, the cube stays `float32`

The dot product and the pixel norm are computed through the `dtype` parameter of
`np.einsum`, which fixes the accumulator of the sum **without casting the cube**.

Measured on a 9-band cube against the same computation in pure `float64`:

| Cube | `float32` accumulator (before) | `float64` accumulator (now) |
|------|--------------------------------|------------------------------|
| Arbitrary pixels | 3.8 × 10⁻⁷ rad | 2.9 × 10⁻⁸ rad |
| Pixels nearly identical to the signature | **4.5 × 10⁻⁴ rad** | 3.9 × 10⁻⁸ rad |

**The deciding row is the second, because it is the regime of a detection.**
Near cosine = 1 the derivative of `arccos` diverges and amplifies rounding: in
that measurement the true angle was 1.3 × 10⁻⁵ rad, meaning the error was **35
times larger than the quantity being measured**. The angle was noise exactly
where the map claims to have found something.

The memory cost is zero, which is what had to be checked before choosing. The
real AOI cube, `(12, 2000, 2000)`, still occupies 183 MB in `float32`; a
`cube.astype(np.float64)` would have cost 366 MB and gives exactly the same
error as the accumulator (3.9 × 10⁻⁸ rad). The only things materialised in
`float64` are the two `(height, width)` maps, 30.5 MB each.

What it does not fix: angles very close to 0 and π keep an error floor of
~2 × 10⁻⁸ rad, because that is the intrinsic sensitivity of `arccos` at ±1 and
not an accumulation problem. It is irreducible while the score is the angle
rather than its cosine.

### The test cases are analytic, not comparative

`tests/test_sam.py` verifies angles whose exact value is known **by geometric
construction** (orthogonal → π/2, `[1,0]` against `[1,1]` → π/4, `[1,0,0]`
against `[1,1,√2]` → π/3, `[1,0]` against `[√3,1]` → π/6, antiparallel → π),
not by comparing against another SAM implementation: two implementations that
agree only prove that they agree, even if both are wrong in the same way. The
exact cases are checked to `1e-12`; the two that fall at the extremes of
`arccos`, to `1e-7`, because of the error floor described above.

There is also an oracle test comparing the vectorised version against a naive
`for` loop over a non-square cube. That is the one that catches an axis error in
the `einsum`: a mis-written `"bhw,b->hw"` raises nothing, it returns a
transposed map that looks perfectly reasonable.

### Resolved: each detector declares its direction and its bands

`Detector.predict` used to document "the higher the value, the stronger the
evidence" and `SAM.predict` returns an angle, where **lower is more similar**.
The debt was left open in Week 3 with a review date of "at the close of Week 4,
and in any case before the first commit of the second detector". **It was
brought forward**, because Week 3 also published a false architectural claim —
`pipeline.py` and this very section said the flow does not name SAM, and it
named it in five places — and the honest exit was to make the claim true, not to
delete the sentence.

**Exit 1 was chosen**: the direction is declared by each detector in the
`higher_is_better` class attribute, and whoever binarises uses
`Detector.detects()`. Normalising everything to "higher is better" (for SAM,
returning the cosine) was not chosen, for three reasons in order: document 05 of
the project defines the SAM score as the angle, and changing SAM to fit an
internal contract would invert the hierarchy of sources; the angle in radians is
the standard SAM unit in the remote sensing literature, and the cosine loses the
physical unit and makes the map incomparable with any publication; and
`viridis_r`, `angle_threshold_rad` and the `<=` in `threshold()` are already all
on the same side, whereas exit 2 forces touching all three.

The change **flips no sign and moves no pixel** of the output: `SAM` declares
`higher_is_better = False`, which is exactly what the pipeline was assuming.
What changed is that it is now written down rather than presumed.

**Which failure it fixed.** A detector registered in `DETECTORS` that respected
the contract — higher value, stronger evidence — and returned 0.9 across the
whole AOI, i.e. maximum evidence, made the sweep report zero pixels under all
five thresholds, **raising nothing**, because the pipeline applied SAM's `<=` to
any score. It would have been found on the day of the first Random Forest
commit, with the whole pipeline running and reporting zero.

Alongside the direction come the **bands**: `Detector.bands` states which bands
the detector consumes and in what order, and the pipeline subsets the cube and
requests the reference signature with that list. It used to trim to `SAM_BANDS`
unconditionally, so a detector with different spectral needs got those nine
anyway. `SAM` declares `bands = tuple(SAM_BANDS)`.

`threshold(angle_map, max_angle)` is kept as is: it is public, it has tests and
other consumers. The only change is that the pipeline no longer uses it.

**What was deliberately not generalised.** These surfaces remain specific to the
spectral angle, and rightly so while the second detector does not exist:

- The `angle_threshold_rad` key in the configs.
- The `angle` and `angle_map_path` keys of the dict `run_pipeline` returns.
- The `Angulo (rad)` line of `_imprimir_resumen` and the `THRESHOLD_SWEEP`
  constant, whose five values are in radians.

None of them produces a silently wrong result: they are names and units, and the
comparison that really could have been wrong is now made by `detects()`.
Generalising them now is speculative churn before knowing what the second
detector needs; they get renamed when it lands and there is something to rename
them against.


## 9. The ground-truth layer

Three Week 4 decisions that have to survive being said out loud.

### 9.1 The Calama sheet does not apply; Pozo Almonte and Mamina replace it

The original plan named the "Calama sheet" as the ground-truth source. **It is
useless here**: Calama is in the Antofagasta Region, around 22.45° S / 68.93° W,
some 250 km south of the AOI. It is a leftover from when the study area was
Chuquicamata (see section 3): the area moved to Pampa del Tamarugal in Week 2
and the written plan was never updated.

The SERNAGEOMIN 1:100,000 sheets that do cover the AOI are **two**:

| Sheet | Code | Geologia Basica series | Year | Coverage |
|---|---|---|---|---|
| Pozo Almonte | M204 | 162–163 (with Iquique) | 2013 | 70.00°–69.50° W · 20.50°–20.00° S |
| Mamina | M303 | 174 | 2015 | 69.50°–69.00° W · 20.50°–20.00° S |

The AOI spans −69.7673° to −69.383° of longitude and **straddles the boundary**
between them: the western half falls in Pozo Almonte, the eastern half in
Mamina. Both must be loaded and merged. Measured on the downloaded data, their
union covers the AOI fully (1600.0 of 1600 km²) and the sheets overlap in a
narrow strip (E 447,510–447,677), so the seam leaves no gap.
`tests/test_geology.py` checks both, when the GeoJSON files are on disk.

The vectors come from the `Chile_Geology` FeatureServer, a **third-party
digitisation with no declared licence**. It is used as a technical input; the
citation that counts is always the original sheet. See
`data/external/geologia/README.md`.

### 9.2 There is no alteration layer: we pick the positive ourselves

SERNAGEOMIN publishes a single cartographic theme ("Geologia Basica"), publishes
no WFS, and has no alteration service in its ArcGIS organisation. **There is no
open layer of hydrothermal alteration polygons for northern Chile.** Risk R5 in
document 08 anticipated this; this confirms it.

The consequence is the central decision of the week: ground truth is **not
obtained by filtering a column**. The sheets carry lithology. The positive class
is a **selection of lithological units** that the team declares acceptable as
compatible with argillic alteration, and that is a geological judgement, not a
fact from the map.

That is why the selection is not in the code: it lives in
`configs/verdad_terreno_cerro_colorado.yaml`, versioned, with one line of
justification per unit and the full list of the 38 units present in the AOI with
their areas. It is the first thing anyone will challenge in a defence, and they
have to be able to challenge it by reading a YAML, not by reading Python.

**A finding to state in the defence before anyone asks:** there is no candidate
alteration unit inside this AOI. The three that were expected exist in the
Mamina sheet and all fall outside it:

| Unit | Distance from the AOI's eastern edge |
|---|---|
| Tourmaline hydrothermal breccias (Yabricoya Complex) | 29.5 km |
| Cerro Colorado intrusive complex | 10.3 km |
| Yabricoya Complex (all facies) | 19.1 km |

The AOI sits entirely on the sedimentary fill of the Pampa del Tamarugal: 96 %
alluvial, saline, aeolian and piedmont deposits. It is a basin fill, not the
porphyry district. The layer still serves to measure **false positives** against
a well-founded negative, which is the question the angle map cannot answer on
its own; what it cannot support is a recall estimate. Measuring positive
detection requires moving or widening the AOI some 10–30 km east, and that is a
project-scope decision.

### 9.3 The `ambiguous` class exists and is not collapsed to 0

The layer carries three values, not two:

| Value | Meaning |
|---|---|
| `1` | Positive: unit accepted as compatible with argillic alteration |
| `0` | Negative: clearly non-candidate unit (salars, aeolian, recent alluvial, gravels) |
| `255` | Ambiguous: unclassified unit, or pixel outside every polygon |

The `255` pixels are **excluded** from the metric computation. Forcing a 0/1
binary would turn "I don't know" into "there is none", which on a class this
imbalanced is exactly the substitution that inflates precision without anything
failing: every doubtful pixel would start counting as a true negative and would
pad the specificity denominator with cases nobody verified.

`255` is also the **default** for anything the YAML does not name, and the fill
for anything no polygon covers. Silence means "I don't know", never "there is
none". `clasificar_unidades` warns via `warnings.warn` how many units were left
unclassified and what fraction of the area they cover, so that a badly filled
YAML cannot silently produce a 100 % ambiguous layer that looks exactly like a
correct one.

### 9.4 `all_touched=False` when rasterising

A pixel belongs to the polygon that **covers its centre**. With
`all_touched=True` every pixel the polygon merely grazes would be marked, which
fattens each positive area by a full one-pixel ring precisely at the edges —
where a 1:100,000 sheet is least reliable against 20 m pixels. Contact precision
between units on that sheet is several pixels wide; widening it on purpose only
adds positive area that cannot be defended.

Two related details, both tested:

- **Reprojection always happens** via `.to_crs(scene.crs)` before rasterising,
  even when the polygons already arrive in 32719. It is idempotent in that case
  and it is the safety net against the one failure mode that goes unnoticed:
  coordinates in degrees against a `transform` in metres raise nothing, they
  simply mark nothing, and the layer comes out entirely `ambiguous` — which is
  exactly what a correct layer looks like with the YAML left empty.
- **`scene.mask` is not applied.** Whether a pixel is valid (cloud, shadow,
  water) and whether it is covered by the mapping are two different things, and
  the consumer is who combines them. Same criterion by which `scene_builder`
  hands back the SCL mask separately instead of applying it to the cube.
- Where two polygons overlap, **the higher class value wins**, i.e. positive
  over negative. The two sheets genuinely overlap, so the case occurs. Positive
  is chosen because it is the rare class: erasing it with a negative would make
  it vanish without a trace, whereas the reverse only adds positive area that is
  visible in the figure.


## 10. The Week 5 AOI move

Three decisions that have to survive being challenged.

### 10.1 Why the AOI moved: E3 could not be met

Week 4 delivered the ground-truth layer and, in building it, the problem
surfaced: **inside the Pampa del Tamarugal AOI there was not a single unit with
mapped hydrothermal alteration**. 96 % of the AOI was sedimentary fill —
alluvial, saline, aeolian and piedmont deposits — and the three candidate units
of the Mamina sheet all fell outside:

| Unit | Distance from the old AOI's eastern edge |
|---|---|
| Tourmaline hydrothermal breccias (Yabricoya Complex) | 29.5 km |
| Cerro Colorado intrusive complex | 10.3 km |
| Yabricoya Complex (all facies) | 19.1 km |

With zero documented alteration zones, criterion **E3** of the master plan —
"detections concentrate preferentially in documented argillic/hydrothermal
alteration zones" — could not even be stated, and neither could **E4** (recall,
F1, ROC/AUC). It is not that the result was poor: the question was meaningless
over that crop.

The answer was to move the window, not to restate the criterion. The window goes
from `col_off=1000, row_off=1000` to `col_off=2700, row_off=650`. **It does not
grow**: still 2000 × 2000 px at 20 m, i.e. 40 × 40 km, and the `.npz` weighs the
same.

`row_off` drops from 1000 to 650 because **Cerro Colorado lies to the northeast,
not merely east**: its southern edge (N 7,782,431) sat 2.4 km above the old
AOI's northern edge, so widening eastwards alone would have left it out. With
the new window all three units come in — Yabricoya is clipped at its eastern
edge, 5.9 km — and the mapping still covers the AOI fully.

What changed in the figures:

| | Tamarugal AOI | Cerro Colorado AOI |
|---|---|---|
| Window | `col_off=1000, row_off=1000` | `col_off=2700, row_off=650` |
| Valid pixels | 99.9977 % (92 discarded) | 99.8484 % (6,064 discarded) |
| Angle min / median / max | 0.0723 / 0.2742 / 0.6971 | 0.0662 / 0.2795 / 0.6859 |
| Detections at 0.1 rad | 62 | 131 |
| Positive in the ground truth | 0 px | 50,773 px (1.27 %) |

The drop in valid pixels is topographic shadow: the window reaches into the
Precordillera and has relief. 0.15 % remains negligible.

### 10.2 What was declared positive, and on what criterion

`configs/verdad_terreno_cerro_colorado.yaml` declares **8 units as positive**
(20.30 km², 1.27 % of the AOI): the tourmaline hydrothermal breccias, both
facies of the Cerro Colorado intrusive complex and the felsic porphyries —
dacitic, rhyodacitic and rhyolitic — including those of the Yabricoya Complex.
The criterion is hydrothermal alteration declared on the sheet, or felsic
porphyritic lithology of the district.

**Ten units are negative** (76.94 km², 4.81 %): active aeolian, active alluvial,
colluvial, landslide deposits and agricultural cover. Everything else stays
ambiguous (93.92 %) and is excluded from the metric computation.

The debatable decision, and it should be stated before anyone asks: **the
plutonic facies of the Yabricoya Complex are not positive** despite belonging to
the complex. They are 81.65 km², four times the entire positive class. They are
monzogranites and syenogranites, i.e. batholith country rock, not the
mineralised porphyry system; including them would multiply the positive class
fivefold with no declared alteration and dilute it into uselessness as a
reference.

### 10.3 How the mine was classified, and why that decides E3

The operating Cerro Colorado mine sits inside the AOI. The sheet records it as
`Depositos antropicos, botaderos de mina`: **16.79 km², 1.05 % of the AOI**.

It was classified as **ambiguous, explicitly and not by omission**. Both readings
are real and they cancel out:

- For positive: a porphyry's waste rock *is* altered rock, crushed and exposed.
  Spectrally it may be the clay-richest visible surface in the AOI.
- For negative: a waste dump is not a mapped alteration zone but a human
  earthwork, and its location is not that of the original rock.
- And there is circularity: the mine is there **because** there is alteration.
  Declaring it positive all but guarantees a hit at the most conspicuous point
  on the map and would inflate the result with no geological backing.

**That decision decides the answer to E3 outright**, and the data confirms it: of
the 131 detections at 0.1 rad, **130 land exactly on the waste dumps**. With the
dumps declared positive, 99.2 % of detections would fall in the positive class
and E3 would be met spectacularly. Under the classification adopted, **zero
detections fall in positive and E3 is not met**.

Honesty requires stating both and leaving the decision where it can be reviewed.
What no classification changes is the bare fact: within the mapped alteration
units the minimum angle is 0.1541 rad, well above the threshold. **No *in situ*
alteration zone in the AOI resembles kaolinite at 20 m resolution.** The likeliest
explanation is that desert crust and varnish mask the signature on the natural
surface, while the mine's disturbed material exposes it.
