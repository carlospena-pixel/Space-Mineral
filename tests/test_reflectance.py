"""Pruebas del escalado DN -> reflectancia y de la lectura del XML del producto."""

import numpy as np
import pytest

from mineralmap.preprocessing.reflectance import dn_to_reflectance, read_l2a_scaling

# XML minimo con namespace por defecto: replica la estructura del
# MTD_MSIL2A.xml real lo justo para ejercitar el parseo sin traer 2 MB de
# metadatos. El namespace esta a proposito, para verificar que el parseo no se
# ancla a el.
XML_SINTETICO = """<?xml version="1.0" encoding="UTF-8"?>
<n1:Level-2A_User_Product
    xmlns:n1="https://psd-14.sentinel2.eo.esa.int/PSD/User_Product_Level-2A.xsd">
  <n1:General_Info>
    <Product_Info>
      <PROCESSING_BASELINE>05.11</PROCESSING_BASELINE>
    </Product_Info>
    <Product_Image_Characteristics>
      <QUANTIFICATION_VALUES_LIST>
        <BOA_QUANTIFICATION_VALUE unit="none">10000</BOA_QUANTIFICATION_VALUE>
        <AOT_QUANTIFICATION_VALUE unit="none">1000.0</AOT_QUANTIFICATION_VALUE>
      </QUANTIFICATION_VALUES_LIST>
      <BOA_ADD_OFFSET_VALUES_LIST>
        <BOA_ADD_OFFSET band_id="0">-1000</BOA_ADD_OFFSET>
        <BOA_ADD_OFFSET band_id="1">-1000</BOA_ADD_OFFSET>
      </BOA_ADD_OFFSET_VALUES_LIST>
    </Product_Image_Characteristics>
  </n1:General_Info>
</n1:Level-2A_User_Product>
"""


def test_baseline_moderno_aplica_offset():
    """Con baseline >= 04.00, DN 3000 son 0.2 de reflectancia (se resta 1000)."""
    dn = np.full((2, 2), 3000, dtype=np.uint16)
    reflectancia = dn_to_reflectance(dn, baseline="05.11")

    assert reflectancia.dtype == np.float32
    assert np.allclose(reflectancia, 0.2)


def test_baseline_antiguo_no_aplica_offset():
    """Con baseline < 04.00 no hay desplazamiento: DN 3000 son 0.3."""
    dn = np.full((2, 2), 3000, dtype=np.uint16)
    reflectancia = dn_to_reflectance(dn, baseline="03.01")

    assert np.allclose(reflectancia, 0.3)


def test_nodata_pasa_a_nan_sin_tocar_el_resto():
    """DN 0 es "sin dato": debe quedar NaN, no convertirse en un 0.0 valido."""
    dn = np.array([[0, 3000], [5000, 0]], dtype=np.uint16)
    reflectancia = dn_to_reflectance(dn, baseline="05.11")

    assert np.isnan(reflectancia[0, 0])
    assert np.isnan(reflectancia[1, 1])
    assert np.allclose(reflectancia[0, 1], 0.2)
    assert np.allclose(reflectancia[1, 0], 0.4)


def test_clip_recorta_a_cero_uno_y_preserva_nan():
    """El clip acota a [0,1] pero no convierte los NaN en 0 ni en 1."""
    # 500 -> -0.05 (por debajo de 0); 20000 -> 1.9 (por encima de 1); 0 -> NaN.
    dn = np.array([[500, 20000, 0]], dtype=np.uint16)
    reflectancia = dn_to_reflectance(dn, baseline="05.11", clip=True)

    assert reflectancia[0, 0] == 0.0
    assert reflectancia[0, 1] == 1.0
    assert np.isnan(reflectancia[0, 2])

    # Sin clip, los valores fuera de rango se conservan tal cual.
    sin_clip = dn_to_reflectance(dn, baseline="05.11", clip=False)
    assert np.allclose(sin_clip[0, 0], -0.05)
    assert np.allclose(sin_clip[0, 1], 1.9)


def test_offset_explicito_gana_al_derivado_del_baseline():
    """Si el llamador pasa el offset del XML, ese manda sobre la regla."""
    dn = np.full((2, 2), 3000, dtype=np.uint16)
    reflectancia = dn_to_reflectance(dn, baseline="05.11", offset=0.0)

    # Con la regla del baseline habria dado 0.2; con offset explicito, 0.3.
    assert np.allclose(reflectancia, 0.3)


def test_read_l2a_scaling_parsea_xml_con_namespace(tmp_path):
    """Lee baseline, offset y cuantificacion pese al namespace del PSD."""
    (tmp_path / "MTD_MSIL2A.xml").write_text(XML_SINTETICO, encoding="utf-8")

    assert read_l2a_scaling(str(tmp_path)) == ("05.11", -1000.0, 10000.0)


def test_read_l2a_scaling_sin_xml_avisa_y_usa_fallback(tmp_path):
    """Sin XML no revienta: devuelve el fallback y lo dice."""
    inexistente = tmp_path / "no_existe.SAFE"

    with pytest.warns(UserWarning, match="MTD_MSIL2A.xml"):
        baseline, offset, quantification = read_l2a_scaling(str(inexistente))

    assert baseline == "04.00"
    assert offset == -1000.0
    assert quantification == 10000.0
