"""Registro de minerales objetivo y sus firmas espectrales de referencia."""

ENDMEMBERS = {
    "kaolinite": {"usgs_sample_id": "KGa-1"},
    # "alunite": {"usgs_sample_id": "..."},
    # "hematite": {"usgs_sample_id": "..."},
}


def get_endmember(name: str):
    raise NotImplementedError
