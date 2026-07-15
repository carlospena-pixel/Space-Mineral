# Spectral Mineral Mapping

**ES** | [EN](#en)

Detección de minerales de alteración hidrotermal (caolinita, alunita, hematita, ...) a
partir de imágenes Sentinel-2 L2A, comparando contra la librería espectral USGS
splib07 y validando contra cartografía geológica de SERNAGEOMIN.

El repositorio está diseñado para escalar de **Nivel 1** (Spectral Angle Mapper) a
**Nivel 2** (Random Forest, más minerales) y **Nivel 3** (unmixing, validación
estadística formal, interfaz para geólogo) sin refactorizar. Ver
`docs/es/decisiones_tecnicas.md` y `docs/es/pipeline.md` para el detalle.

## Quickstart

```bash
# Entorno reproducible (rasterio/gdal vía conda-forge)
conda env create -f environment.yml
conda activate mineralmap

# Paquete instalable en modo editable
pip install -e ".[dev]"
pre-commit install

# Correr un experimento
python scripts/run_pipeline.py configs/chuqui_kaolinite.yaml
python scripts/evaluate.py data/processed/chuqui_kaolinite/score_map.tif data/external/sernageomin/...
```

Los datos (`data/`) no se versionan; ver `docs/es/pipeline.md` para cómo obtenerlos.

## Estructura

```
configs/      Experimentos declarativos (YAML)
data/         Datos crudos/externos/intermedios/procesados (no versionado)
src/mineralmap/  Paquete instalable: io, preprocessing, spectral, algorithms, validation, visualization
scripts/      Entrypoints CLI delgados
notebooks/    Exploración y prototipado
tests/        pytest
docs/         Documentación extendida (ES/EN)
outputs/      Figuras y mapas exportados (no versionado)
```

## Resultados

_Pendiente: se completa a medida que corren los experimentos de cada nivel._

---

<a id="en"></a>
## English

Detection of hydrothermal alteration minerals (kaolinite, alunite, hematite, ...) from
Sentinel-2 L2A imagery, matched against the USGS splib07 spectral library and
validated against SERNAGEOMIN geological mapping.

The repository is designed to scale from **Level 1** (Spectral Angle Mapper) to
**Level 2** (Random Forest, more minerals) and **Level 3** (unmixing, formal
statistical validation, geologist-facing interface) without refactoring. See
`docs/en/technical_decisions.md` and `docs/en/pipeline.md` for details.

### Quickstart

```bash
conda env create -f environment.yml
conda activate mineralmap

pip install -e ".[dev]"
pre-commit install

python scripts/run_pipeline.py configs/chuqui_kaolinite.yaml
```

`data/` is not versioned; see `docs/en/pipeline.md` for how to obtain it.

### Results

_Pending: filled in as experiments for each level are run._

## License

MIT — see [LICENSE](LICENSE).
