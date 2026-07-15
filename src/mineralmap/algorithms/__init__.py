"""algorithms: recibe un cubo y una referencia, y devuelve un mapa de puntaje.

base.py define el contrato (Detector.fit/Detector.predict) que SAM, Random Forest
y unmixing cumplen por igual. Este es el mecanismo de escalabilidad: el pipeline
no sabe que algoritmo usa, solo llama a la interfaz.
"""
