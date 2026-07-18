
import numpy as np

def aplicar_mascara_scl(banda_scl, cubo_datos):
    """
    Enmascara (convierte a NaN) los píxeles de nubes, sombras y agua.
    Valores SCL: 3 (sombra nube), 6 (agua), 8 (nube severa), 9 (nube densa), 10 (cirrus).
    """
    # Creamos una máscara booleana donde True significa "Píxel Malo"
    mascara_nubes_agua = np.isin(banda_scl, [3, 6, 8, 9, 10])
    
    # Aplicamos NaN a esos píxeles en todas las bandas del cubo
    cubo_limpio = np.copy(cubo_datos)
    cubo_limpio[:, mascara_nubes_agua] = np.nan
    
    # Devolvemos el cubo limpio y una máscara de válidos (True = Suelo/Vegetación)
    mascara_validos = ~mascara_nubes_agua
    return cubo_limpio, mascara_validos

def test_masking():
    # Simulamos una banda SCL de 3x3
    # 5 = Suelo, 6 = Agua, 9 = Nube
    scl_mock = np.array([
        [5, 5, 6],
        [5, 9, 5],
        [3, 5, 5]
    ])
    
    # Simulamos un cubo de datos de 2 bandas, 3x3 píxeles
    cubo_mock = np.ones((2, 3, 3)) 
    
    cubo_limpio, mask = aplicar_mascara_scl(scl_mock, cubo_mock)
    
    # Comprobamos que el agua (6), nube (9) y sombra (3) se volvieron NaN
    assert np.isnan(cubo_limpio[0, 0, 2]), "Error: El agua no se enmascaró."
    assert np.isnan(cubo_limpio[0, 1, 1]), "Error: La nube no se enmascaró."
    assert np.isnan(cubo_limpio[0, 2, 0]), "Error: La sombra no se enmascaró."
    
    # Comprobamos que el suelo desnudo (5) se mantuvo intacto
    assert cubo_limpio[0, 0, 0] == 1.0, "Error: El suelo desnudo se alteró."
    print("¡Test test_masking.py PASÓ con éxito! La lógica de enmascarado es correcta.")

if __name__ == "__main__":
    test_masking()