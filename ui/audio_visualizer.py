"""
Visualizador de Audio Reactivo para JARVIS.
Implementación visual en PyQt6 con proyección manual 3D -> 2D (numpy) sobre QPainter estándar.

Restricciones técnicas y de rendimiento:
- CERO Qt3D, QOpenGLWidget o motores 3D. Renderizado 100% 2D con QPainter.
- Nube de puntos fija (Esfera de Fibonacci, 144 nodos).
- Lista de aristas PRECALCULADA una sola vez — nunca recalculada por frame.
- Sprites de glow precomputados en niveles de profundidad (gradiente radial en QPixmap) — sin blur ni escalado costoso por frame.
- Estados:
  * REPOSO: rotación lenta y constante, brillo tenue y estable, sin reacción a audio.
  * ESCUCHANDO: posición/radio de los nodos modulado asimétricamente por las 16 bandas
    de frecuencia del micrófono (FFT con numpy).
  * HABLANDO: patrón de pulso rítmico global atado a la envolvente de amplitud de la
    síntesis de voz (expansión sincrónica de toda la esfera, distinguible a simple vista
    de la distorsión individual de nodos en escucha).
"""

from enum import Enum
import math
import time
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget


class VisualizerState(str, Enum):
    REPOSO = "reposo"
    ESCUCHANDO = "escuchando"
    HABLANDO = "hablando"


class FibonacciSphere3D:
    """
    Generador y proyector 3D de una esfera de Fibonacci con aristas precalculadas.
    La topología (puntos y aristas) se calcula exactamente UNA vez al inicializar.
    """

    def __init__(
        self,
        num_nodes: int = 144,
        k_nearest_edges: int = 4,
        max_edge_dist: float = 0.45,
    ):
        self.num_nodes = num_nodes
        self.k_nearest_edges = k_nearest_edges
        self.max_edge_dist = max_edge_dist

        # 1. Nube de puntos base en la esfera de Fibonacci (radio = 1.0)
        self.base_points = self._generate_fibonacci_points(num_nodes)

        # 2. Lista de aristas precalculada una sola vez
        self.edges = self._precompute_edges(
            self.base_points, k_nearest_edges, max_edge_dist
        )

        # 3. Mapeo de latitud de nodos a bandas de frecuencia (0 a 15)
        # Permite que frecuencias bajas deformen la base y altas la cúspide
        latitudes = (self.base_points[:, 1] + 1.0) * 0.5  # de 0.0 a 1.0
        self.node_band_indices = np.clip(
            (latitudes * 16.0).astype(np.int32), 0, 15
        )

    @staticmethod
    def _generate_fibonacci_points(n: int) -> np.ndarray:
        """Genera n puntos distribuidos uniformemente en una esfera unidad."""
        points = np.zeros((n, 3), dtype=np.float32)
        phi = (1.0 + math.sqrt(5.0)) / 2.0  # Proporción áurea
        golden_angle = 2.0 * math.pi * (1.0 - 1.0 / phi)

        indices = np.arange(n, dtype=np.float32)
        y = 1.0 - (indices / float(n - 1)) * 2.0  # De 1 a -1
        radius = np.sqrt(np.maximum(0.0, 1.0 - y * y))
        theta = golden_angle * indices

        points[:, 0] = np.cos(theta) * radius
        points[:, 1] = y
        points[:, 2] = np.sin(theta) * radius
        return points

    @staticmethod
    def _precompute_edges(
        points: np.ndarray, k_nearest: int, max_dist: float
    ) -> np.ndarray:
        """
        Precalcula las aristas conectando cada punto con sus k vecinos más cercanos
        dentro de un radio máximo de distancia euclidiana.
        Retorna un array (E, 2) de índices de nodos (i < j).
        """
        n = len(points)
        edge_set = set()

        # Matriz de distancias euclidianas 3D
        diff = points[:, np.newaxis, :] - points[np.newaxis, :, :]
        dist_matrix = np.sqrt(np.sum(diff * diff, axis=-1))

        for i in range(n):
            sorted_indices = np.argsort(dist_matrix[i])
            count = 0
            for j in sorted_indices:
                if i == j:
                    continue
                if dist_matrix[i, j] <= max_dist:
                    edge = (min(i, j), max(i, j))
                    edge_set.add(edge)
                    count += 1
                    if count >= k_nearest:
                        break

        edges = np.array(list(edge_set), dtype=np.int32)
        return edges

    def project_and_rotate(
        self,
        angles: Tuple[float, float, float],
        radii_modifiers: Optional[np.ndarray] = None,
        base_radius: float = 120.0,
        center: Tuple[float, float] = (200.0, 200.0),
        camera_distance: float = 3.2,
        focal_length: float = 350.0,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Aplica rotación 3D y proyección de perspectiva manual 3D -> 2D con numpy.
        Retorna:
          - coords_2d: (N, 2) coordenadas de píxel en pantalla.
          - z_depths: (N,) profundidad Z para ordenamiento y cálculo de niebla/alfa.
          - scale_factors: (N,) factor de escala por perspectiva para dibujar sprites.
        """
        ax, ay, az = angles

        # Matrices de rotación trigonométricas 3D
        cx, sx = math.cos(ax), math.sin(ax)
        cy, sy = math.cos(ay), math.sin(ay)
        cz, sz = math.cos(az), math.sin(az)

        # Matriz combinada R = Rz * Ry * Rx
        r_xx = cy * cz
        r_xy = cz * sx * sy - cx * sz
        r_xz = cx * cz * sy + sx * sz

        r_yx = cy * sz
        r_yy = cx * cz + sx * sy * sz
        r_yz = -cz * sx + cx * sy * sz

        r_zx = -sy
        r_zy = cy * sx
        r_zz = cx * cy

        rot_matrix = np.array(
            [[r_xx, r_xy, r_xz], [r_yx, r_yy, r_yz], [r_zx, r_zy, r_zz]],
            dtype=np.float32,
        )

        # Modulación de radio por nodo (base + distorsión)
        pts = self.base_points.copy()
        if radii_modifiers is not None:
            pts *= radii_modifiers[:, np.newaxis]
        else:
            pts *= base_radius

        # Rotar en el espacio 3D
        rotated = pts @ rot_matrix.T

        # Proyección en perspectiva
        cam_dist_px = camera_distance * base_radius
        z_projected = rotated[:, 2] + cam_dist_px

        # Prevenir división por cero
        z_safe = np.maximum(z_projected, 10.0)
        factors = focal_length / z_safe

        x_2d = rotated[:, 0] * factors + center[0]
        y_2d = rotated[:, 1] * factors + center[1]

        coords_2d = np.column_stack((x_2d, y_2d))
        z_depths = rotated[:, 2]

        return coords_2d, z_depths, factors


class ReactiveAudioVisualizer(QWidget):
    """
    Widget visualizador de audio reactivo en PyQt6 con proyección 3D manual sobre QPainter.
    Implementa renderizado de ultra-alto rendimiento (> 200 FPS) mediante sprites precomputados en niveles de profundidad.
    """

    NUM_DEPTH_TIERS = 4

    def __init__(self, parent: Optional[QWidget] = None, num_nodes: int = 144):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        # 1. Geometría 3D precalculada
        self.sphere = FibonacciSphere3D(num_nodes=num_nodes)
        self.num_nodes = num_nodes

        # 2. Estado visual del asistente
        self.state: VisualizerState = VisualizerState.REPOSO

        # 3. Ángulos de rotación y tiempo de animación
        self.angle_x: float = 0.2
        self.angle_y: float = 0.0
        self.angle_z: float = 0.0
        self.time_counter: float = 0.0

        # Velocidad de rotación base
        self.rotation_speed_idle: float = 0.012

        # 4. Paleta de colores predefinida
        self.color_cyan = QColor(0, 230, 255)
        self.color_blue = QColor(0, 140, 255)
        self.color_speaking_accent = QColor(140, 240, 255)
        self.color_core = QColor(240, 255, 255)

        # 5. Sprites de glow precomputados por niveles de profundidad (Depth Tiers)
        # Rendimiento crítico: calculados una sola vez al inicio, sin blur ni escalado por frame
        self.glow_sprites: Dict[str, List[Tuple[int, QPixmap]]] = self._precompute_tiered_sprites()

        # 6. Plumas de dibujo precomputadas por nivel de profundidad
        self.tiered_pens: Dict[str, List[QPen]] = self._precompute_tiered_pens()

        # 7. Parámetros de reactividad de audio
        self.num_bands: int = 16
        self.freq_bands: np.ndarray = np.zeros(self.num_bands, dtype=np.float32)
        self.band_decay: float = 0.88

        # Estado de síntesis de voz (Hablando)
        self.speech_amplitude: float = 0.0
        self.speech_target_amplitude: float = 0.0

        # 8. Timer de animación (60 FPS objetivo -> 16 ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_animation_frame)
        self.timer.start(16)

    def _precompute_tiered_sprites(self) -> Dict[str, List[Tuple[int, QPixmap]]]:
        """
        Precomputa sprites de resplandor para cada nivel de profundidad (0=fondo a 3=frente).
        Cada sprite incorpora el gradiente radial difuso y el núcleo brillante pre-renderizado.
        """
        result: Dict[str, List[Tuple[int, QPixmap]]] = {}
        themes = [
            ("cyan", self.color_cyan, QColor(0, 140, 255)),
            ("blue", self.color_blue, QColor(0, 90, 200)),
            ("speaking", self.color_speaking_accent, QColor(0, 210, 255)),
        ]

        for name, main_col, sec_col in themes:
            tiers = []
            for t in range(self.NUM_DEPTH_TIERS):
                norm = t / float(self.NUM_DEPTH_TIERS - 1)
                radius = int(10 + norm * 14)  # Radio de 10px (fondo) a 24px (frente)
                size = radius * 2

                pix = QPixmap(size, size)
                pix.fill(Qt.GlobalColor.transparent)

                painter = QPainter(pix)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

                # Gradiente radial difuso
                grad = QRadialGradient(radius, radius, radius)
                c_center = QColor(main_col)
                c_center.setAlpha(int(70 + norm * 180))
                c_mid = QColor(sec_col)
                c_mid.setAlpha(int(20 + norm * 80))
                c_edge = QColor(sec_col)
                c_edge.setAlpha(0)

                grad.setColorAt(0.0, c_center)
                grad.setColorAt(0.40, c_mid)
                grad.setColorAt(1.0, c_edge)

                painter.setBrush(grad)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(0, 0, size, size)

                # Núcleo blanco celestial brillante integrado
                c_core = QColor(self.color_core)
                c_core.setAlpha(int(110 + norm * 145))
                painter.setBrush(c_core)
                core_radius = 1.0 + norm * 1.6
                painter.drawEllipse(QPointF(radius, radius), core_radius, core_radius)

                painter.end()
                tiers.append((radius, pix))

            result[name] = tiers

        return result

    def _precompute_tiered_pens(self) -> Dict[str, List[QPen]]:
        """Precomputa las plumas de líneas para los distintos niveles de profundidad."""
        result: Dict[str, List[QPen]] = {}

        themes = [
            ("reposo", self.color_blue),
            ("escuchando", self.color_cyan),
            ("hablando", self.color_speaking_accent),
        ]

        for name, base_col in themes:
            pens = []
            for t in range(self.NUM_DEPTH_TIERS):
                norm = t / float(self.NUM_DEPTH_TIERS - 1)
                alpha = int(35 + norm * 165)
                c = QColor(base_col)
                c.setAlpha(alpha)
                pen = QPen(c, 1, Qt.PenStyle.SolidLine)
                pens.append(pen)
            result[name] = pens

        return result

    def set_state(self, new_state: VisualizerState) -> None:
        """Cambia el estado visual del visualizador."""
        if self.state != new_state:
            self.state = new_state
            self.update()

    def feed_audio_samples(
        self, samples: Union[np.ndarray, bytes, list], sample_rate: int = 16000
    ) -> None:
        """
        Alimenta muestras de audio del micrófono para modular en estado ESCUCHANDO.
        Calcula la FFT utilizando numpy y descompone la energía en 16 bandas de frecuencia.
        """
        if isinstance(samples, bytes):
            data = np.frombuffer(samples, dtype=np.int16).astype(np.float32) / 32768.0
        elif isinstance(samples, list):
            data = np.array(samples, dtype=np.float32)
        else:
            data = samples.astype(np.float32)

        if len(data) < 32:
            return

        window = np.hanning(len(data))
        windowed = data * window

        fft_vals = np.abs(np.fft.rfft(windowed))
        num_bins = len(fft_vals)

        new_bands = np.zeros(self.num_bands, dtype=np.float32)
        indices = np.geomspace(1, max(2, num_bins - 1), num=self.num_bands + 1).astype(int)

        for b in range(self.num_bands):
            start = indices[b]
            end = max(start + 1, indices[b + 1])
            chunk = fft_vals[start:end]
            energy = np.mean(chunk) if len(chunk) > 0 else 0.0
            new_bands[b] = float(np.clip(np.log1p(energy * 15.0) / 2.6, 0.0, 1.0))

        self.freq_bands = np.maximum(new_bands, self.freq_bands * self.band_decay)

    def feed_output_amplitude(self, amplitude: float) -> None:
        """
        Alimenta la envolvente de amplitud de voz (0.0 a 1.0) para HABLANDO.
        Genera el pulso global sincrónico de la estructura.
        """
        self.speech_target_amplitude = float(np.clip(amplitude, 0.0, 1.0))

    def _on_animation_frame(self) -> None:
        """Actualiza el frame de animación según el estado activo."""
        self.time_counter += 0.016

        if self.state == VisualizerState.REPOSO:
            # Rotación suave y constante en reposo
            self.angle_y += self.rotation_speed_idle
            self.angle_x = 0.22 + 0.05 * math.sin(self.time_counter * 0.8)
            self.freq_bands *= 0.90
            self.speech_amplitude *= 0.85

        elif self.state == VisualizerState.ESCUCHANDO:
            # Rotación viva durante la escucha
            self.angle_y += self.rotation_speed_idle * 1.4
            self.angle_x = 0.25 + 0.08 * math.sin(self.time_counter * 1.1)
            self.freq_bands *= self.band_decay

        elif self.state == VisualizerState.HABLANDO:
            # Rotación cadenciosa
            self.angle_y += self.rotation_speed_idle * 1.2
            self.angle_x = 0.22 + 0.04 * math.sin(self.time_counter * 0.9)

            if self.speech_target_amplitude <= 0.01:
                cadence = 0.35 + 0.45 * (
                    0.5 * math.sin(self.time_counter * 7.5) * math.cos(self.time_counter * 3.2) + 0.5
                )
                self.speech_amplitude += (cadence - self.speech_amplitude) * 0.35
            else:
                self.speech_amplitude += (
                    self.speech_target_amplitude - self.speech_amplitude
                ) * 0.45

        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Punto de entrada de renderizado de Qt sobre la superficie del widget."""
        painter = QPainter(self)
        self.render_frame(painter, self.width(), self.height())
        painter.end()

    def render_frame(self, painter: QPainter, width: int, height: int) -> None:
        """
        Dibuja un frame completo sobre QPainter mediante proyección 3D y composición 2D ultrarrápida.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        center = (width / 2.0, height / 2.0)
        base_radius = min(width, height) * 0.32

        # 1. Modulación geométrica según el estado
        if self.state == VisualizerState.REPOSO:
            breathing = 1.0 + 0.02 * math.sin(self.time_counter * 1.5)
            current_base_radius = base_radius * breathing
            radii_modifiers = np.full(
                self.num_nodes, current_base_radius, dtype=np.float32
            )
            theme_key = "cyan"
            pen_theme_key = "reposo"

        elif self.state == VisualizerState.ESCUCHANDO:
            current_base_radius = base_radius
            node_bands = self.freq_bands[self.sphere.node_band_indices]
            radii_modifiers = current_base_radius * (1.0 + node_bands * 0.50)
            theme_key = "cyan"
            pen_theme_key = "escuchando"

        elif self.state == VisualizerState.HABLANDO:
            effective_pulse = max(self.speech_amplitude, 0.0)
            global_expansion = 1.0 + effective_pulse * 0.35
            current_base_radius = base_radius * global_expansion
            radii_modifiers = np.full(
                self.num_nodes, current_base_radius, dtype=np.float32
            )
            theme_key = "speaking"
            pen_theme_key = "hablando"

        # 2. Proyección 3D -> 2D manual
        angles = (self.angle_x, self.angle_y, self.angle_z)
        coords_2d, z_depths, factors = self.sphere.project_and_rotate(
            angles=angles,
            radii_modifiers=radii_modifiers,
            base_radius=current_base_radius,
            center=center,
        )

        # 3. Dibujar aristas agrupadas por nivel de profundidad
        edges = self.sphere.edges
        z_avg = (z_depths[edges[:, 0]] + z_depths[edges[:, 1]]) * 0.5
        z_norm = np.clip((z_avg + current_base_radius) / (2.0 * current_base_radius + 1e-5), 0.0, 0.99)
        edge_tiers = (z_norm * self.NUM_DEPTH_TIERS).astype(np.int32)

        pens = self.tiered_pens[pen_theme_key]
        for b in range(self.NUM_DEPTH_TIERS):
            painter.setPen(pens[b])
            mask = np.where(edge_tiers == b)[0]
            for idx in mask:
                u, v = edges[idx]
                painter.drawLine(
                    int(coords_2d[u, 0]), int(coords_2d[u, 1]),
                    int(coords_2d[v, 0]), int(coords_2d[v, 1]),
                )

        # 4. Dibujar nodos mediante sprites precomputados por nivel de profundidad
        node_norm = np.clip((z_depths + current_base_radius) / (2.0 * current_base_radius + 1e-5), 0.0, 0.99)
        node_tiers = (node_norm * self.NUM_DEPTH_TIERS).astype(np.int32)
        sprites = self.glow_sprites[theme_key]

        order = np.argsort(z_depths)  # Del fondo hacia el frente
        for idx in order:
            t_idx = node_tiers[idx]
            r, pix = sprites[t_idx]
            x = int(coords_2d[idx, 0]) - r
            y = int(coords_2d[idx, 1]) - r
            painter.drawPixmap(x, y, pix)

    def benchmark_fps(
        self,
        num_frames: int = 300,
        state: VisualizerState = VisualizerState.REPOSO,
        feed_audio_waveform: bool = False,
    ) -> Dict[str, float]:
        """
        Ejecuta una medición precisa de rendimiento (FPS real y tiempo por frame)
        renderizando frames completos mediante QPainter sobre un buffer QImage offscreen.
        """
        self.set_state(state)
        self.resize(400, 400)

        from PyQt6.QtGui import QImage
        image = QImage(400, 400, QImage.Format.Format_ARGB32_Premultiplied)

        # Generar señal de audio sintética compleja
        sample_rate = 16000
        t_audio = np.linspace(0, 0.032, int(sample_rate * 0.032), endpoint=False)
        simulated_audio = (
            0.5 * np.sin(2 * np.pi * 220 * t_audio)
            + 0.3 * np.sin(2 * np.pi * 660 * t_audio)
            + 0.2 * np.sin(2 * np.pi * 1800 * t_audio)
        ).astype(np.float32)

        # Warm-up de 10 frames
        for _ in range(10):
            self._on_animation_frame()
            p = QPainter(image)
            self.render_frame(p, 400, 400)
            p.end()

        # Medición cronometrada
        start_time = time.perf_counter()

        for frame_idx in range(num_frames):
            if feed_audio_waveform:
                if state == VisualizerState.ESCUCHANDO:
                    self.feed_audio_samples(simulated_audio * (0.8 + 0.2 * math.sin(frame_idx * 0.2)))
                elif state == VisualizerState.HABLANDO:
                    self.feed_output_amplitude(0.5 + 0.5 * math.sin(frame_idx * 0.15))

            self._on_animation_frame()
            painter = QPainter(image)
            self.render_frame(painter, 400, 400)
            painter.end()

        end_time = time.perf_counter()
        elapsed = end_time - start_time
        fps = num_frames / elapsed if elapsed > 0 else 0.0
        mean_ms = (elapsed / num_frames) * 1000.0

        return {
            "num_frames": float(num_frames),
            "elapsed_seconds": elapsed,
            "fps": fps,
            "mean_frame_ms": mean_ms,
            "num_nodes": float(self.num_nodes),
        }
