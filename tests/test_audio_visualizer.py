"""
Pruebas unitarias para el renderizado base del visualizador de audio reactivo (Commit 1).
Cubre:
1. Generación de esfera de Fibonacci (144 nodos sobre esfera unidad).
2. Lista de aristas precalculada una sola vez.
3. Proyección manual 3D -> 2D con numpy.
4. Generación y disponibilidad de sprites de glow precomputados.
5. Renderizado offscreen mediante QPainter sin excepciones.
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import numpy as np
import pytest
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from ui.audio_visualizer import FibonacciSphere3D, ReactiveAudioVisualizer, VisualizerState


@pytest.fixture(scope="session")
def qapp():
    """Instancia compartida de QApplication para pruebas en modo offscreen."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test_visualizer"])
    return app


def test_fibonacci_sphere_geometry_and_precomputed_edges():
    """Verifica que la esfera de Fibonacci genere la cantidad correcta de nodos y aristas fijas."""
    num_nodes = 144
    sphere = FibonacciSphere3D(num_nodes=num_nodes)

    # 1. Cantidad y dimensión de nodos base
    assert sphere.base_points.shape == (num_nodes, 3)

    # 2. Verificar que todos los nodos residan sobre la esfera unidad (radio = 1.0)
    norms = np.linalg.norm(sphere.base_points, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3), "Todos los puntos base deben estar normalizados a radio 1"

    # 3. Lista de aristas precalculada
    edges = sphere.edges
    assert len(edges) > 0, "La lista de aristas precalculadas no debe estar vacía"
    assert edges.shape[1] == 2, "Las aristas deben ser pares de índices (i, j)"
    assert np.all(edges[:, 0] < edges[:, 1]), "Las aristas deben mantener el orden canónico i < j"
    assert np.all(edges >= 0) and np.all(edges < num_nodes), "Los índices de arista deben estar dentro del rango [0, N)"


def test_fibonacci_sphere_3d_projection():
    """Verifica que la proyección perspectiva 3D -> 2D produzca coordenadas válidas y ordenadas."""
    sphere = FibonacciSphere3D(num_nodes=144)
    center = (250.0, 250.0)
    angles = (0.3, 0.5, 0.1)

    coords_2d, z_depths, factors = sphere.project_and_rotate(
        angles=angles,
        base_radius=100.0,
        center=center,
    )

    assert coords_2d.shape == (144, 2)
    assert z_depths.shape == (144,)
    assert factors.shape == (144,)

    # Las coordenadas proyectadas deben estar alrededor del centro definido
    assert np.all(coords_2d[:, 0] > 0.0) and np.all(coords_2d[:, 0] < 500.0)
    assert np.all(coords_2d[:, 1] > 0.0) and np.all(coords_2d[:, 1] < 500.0)


def test_visualizer_widget_sprites_and_state_machine(qapp):
    """Verifica los sprites precomputados y la máquina de estados del widget."""
    widget = ReactiveAudioVisualizer(num_nodes=144)

    # 1. Sprites precomputados
    assert "cyan" in widget.glow_sprites
    assert "blue" in widget.glow_sprites
    assert "speaking" in widget.glow_sprites
    for name, pix in widget.glow_sprites.items():
        assert not pix.isNull(), f"El sprite '{name}' no debe ser nulo"
        assert pix.width() > 0 and pix.height() > 0

    # 2. Estado inicial y transiciones
    assert widget.state == VisualizerState.REPOSO
    widget.set_state(VisualizerState.ESCUCHANDO)
    assert widget.state == VisualizerState.ESCUCHANDO
    widget.set_state(VisualizerState.HABLANDO)
    assert widget.state == VisualizerState.HABLANDO


def test_visualizer_widget_renders_cleanly_on_qimage(qapp):
    """Verifica que paintEvent renderice en un buffer QImage offscreen sin errores de ejecución."""
    widget = ReactiveAudioVisualizer(num_nodes=144)
    widget.resize(400, 400)

    # Renderizar en un QImage offscreen
    image = QImage(400, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)

    painter = QPainter(image)
    widget.render(painter)
    painter.end()

    # Comprobar que no quedó totalmente negro (se dibujaron píxeles de nodos/aristas)
    # Convertir a array de bytes o comprobar píxeles dibujados
    has_drawn_pixels = False
    for y in range(150, 250, 10):
        for x in range(150, 250, 10):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 0:
                has_drawn_pixels = True
                break
        if has_drawn_pixels:
            break

    assert has_drawn_pixels, "El widget debe haber dibujado píxeles en el canvas 2D"
