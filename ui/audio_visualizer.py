"""
Visualizador de Audio Reactivo para JARVIS.
Implementación visual en PyQt6 con proyección manual 3D -> 2D (numpy) sobre QPainter estándar.

Restricciones técnicas:
- CERO Qt3D, QOpenGLWidget o motores 3D. Renderizado 100% 2D con QPainter.
- Nube de puntos fija (Esfera de Fibonacci, 144 nodos).
- Lista de aristas PRECALCULADA una sola vez — nunca recalculada por frame.
- Sprite de glow precomputado (gradiente radial en QPixmap) — sin blur en tiempo real por frame.
- Estados: REPOSO (rotación suave y brillo estable), ESCUCHANDO, HABLANDO.
"""

from enum import Enum
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
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

        # Matriz de distancias euclidianas euclidiana 3D
        diff = points[:, np.newaxis, :] - points[np.newaxis, :, :]
        dist_matrix = np.sqrt(np.sum(diff * diff, axis=-1))

        for i in range(n):
            # Obtener vecinos más cercanos excluyendo el propio punto (distancia 0)
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
          - coords_2d: (N, 2) coordenadas de píxel en la pantalla.
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
        # z' = rotated[:, 2] + camera_distance * base_radius
        cam_dist_px = camera_distance * base_radius
        z_projected = rotated[:, 2] + cam_dist_px

        # Prevenir división por cero
        z_safe = np.maximum(z_projected, 10.0)
        factors = focal_length / z_safe

        x_2d = rotated[:, 0] * factors + center[0]
        y_2d = rotated[:, 1] * factors + center[1]

        coords_2d = np.column_stack((x_2d, y_2d))
        z_depths = rotated[:, 2]  # Z relativo al centro (-base_radius a +base_radius)

        return coords_2d, z_depths, factors


class ReactiveAudioVisualizer(QWidget):
    """
    Widget visualizador de audio reactivo en PyQt6 con proyección 3D manual sobre QPainter.
    Implementa renderizado de alto rendimiento sin shaders ni blur en tiempo real.
    """

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

        # 4. Paleta de colores predefinida (Cian/Azul estelar, Ámbar cálido)
        self.color_cyan = QColor(0, 230, 255)
        self.color_blue = QColor(0, 140, 255)
        self.color_speaking_accent = QColor(140, 240, 255)
        self.color_core = QColor(240, 255, 255)

        # 5. Sprites de glow precomputados (QPixmap con gradiente radial)
        # Rendimiento crítico: calculados una sola vez al inicio, jamás por frame
        self.glow_sprites: Dict[str, QPixmap] = self._precompute_glow_sprites()

        # 6. Timer de animación (60 FPS objetivo -> 16 ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_animation_frame)
        self.timer.start(16)

    def _precompute_glow_sprites(self) -> Dict[str, QPixmap]:
        """
        Genera sprites de resplandor precomputados en pixmaps con gradientes radiales.
        Evita cualquier cálculo de blur o filtrado costoso por frame.
        """
        sprite_radius = 28
        size = sprite_radius * 2
        sprites: Dict[str, QPixmap] = {}

        for name, base_col in [
            ("cyan", self.color_cyan),
            ("blue", self.color_blue),
            ("speaking", self.color_speaking_accent),
        ]:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            grad = QRadialGradient(sprite_radius, sprite_radius, sprite_radius)
            # Núcleo intenso
            c_center = QColor(base_col)
            c_center.setAlpha(190)
            # Halo medio
            c_mid = QColor(base_col)
            c_mid.setAlpha(55)
            # Difuminado externo
            c_edge = QColor(base_col)
            c_edge.setAlpha(0)

            grad.setColorAt(0.0, c_center)
            grad.setColorAt(0.35, c_mid)
            grad.setColorAt(1.0, c_edge)

            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, size, size)
            painter.end()

            sprites[name] = pixmap

        return sprites

    def set_state(self, new_state: VisualizerState) -> None:
        """Cambia el estado visual del visualizador."""
        if self.state != new_state:
            self.state = new_state
            self.update()

    def _on_animation_frame(self) -> None:
        """Actualiza el frame de animación según el estado activo."""
        self.time_counter += 0.016

        if self.state == VisualizerState.REPOSO:
            # Rotación constante y suave en reposo
            self.angle_y += self.rotation_speed_idle
            self.angle_x = 0.22 + 0.05 * math.sin(self.time_counter * 0.8)
        elif self.state == VisualizerState.ESCUCHANDO:
            # Rotación viva durante la escucha
            self.angle_y += self.rotation_speed_idle * 1.5
            self.angle_x = 0.25 + 0.08 * math.sin(self.time_counter * 1.2)
        elif self.state == VisualizerState.HABLANDO:
            # Rotación cadenciosa
            self.angle_y += self.rotation_speed_idle * 1.2
            self.angle_x = 0.22 + 0.04 * math.sin(self.time_counter * 0.9)

        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Renderizado 2D completo de la esfera 3D proyectada sobre QPainter."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        width = self.width()
        height = self.height()
        center = (width / 2.0, height / 2.0)
        base_radius = min(width, height) * 0.32

        # 1. Cálculo de radio según estado
        # En reposo: respiración sutil
        breathing = 1.0 + 0.02 * math.sin(self.time_counter * 1.5)
        current_base_radius = base_radius * breathing

        # Moduladores de radio por nodo
        radii_modifiers = np.full(
            self.num_nodes, current_base_radius, dtype=np.float32
        )

        # 2. Proyección 3D -> 2D manual
        angles = (self.angle_x, self.angle_y, self.angle_z)
        coords_2d, z_depths, factors = self.sphere.project_and_rotate(
            angles=angles,
            radii_modifiers=radii_modifiers,
            base_radius=current_base_radius,
            center=center,
        )

        # Rango de profundidad Z para mapeo de transparencia (niebla de profundidad)
        max_z = current_base_radius
        min_z = -current_base_radius

        # 3. Dibujar aristas precalculadas
        # Para cada arista, calculamos la opacidad según la profundidad Z promedio
        edges = self.sphere.edges
        edge_pt_a = coords_2d[edges[:, 0]]
        edge_pt_b = coords_2d[edges[:, 1]]
        z_avg = (z_depths[edges[:, 0]] + z_depths[edges[:, 1]]) * 0.5

        # Normalizar z_avg entre 0.0 (fondo) y 1.0 (frente)
        z_norm = np.clip((z_avg - min_z) / (max_z - min_z + 1e-5), 0.0, 1.0)

        # Seleccionar color de línea base según estado
        line_base_color = self.color_blue

        for i in range(len(edges)):
            norm_val = z_norm[i]
            # Aristas lejanas: tenues (alpha ~25); cercanas: nítidas (alpha ~170)
            alpha = int(25 + norm_val * 145)
            width_line = 0.8 + norm_val * 1.1

            pen_color = QColor(line_base_color)
            pen_color.setAlpha(alpha)
            pen = QPen(pen_color, width_line, Qt.PenStyle.SolidLine)
            painter.setPen(pen)

            p1 = QPointF(edge_pt_a[i, 0], edge_pt_a[i, 1])
            p2 = QPointF(edge_pt_b[i, 0], edge_pt_b[i, 1])
            painter.drawLine(p1, p2)

        # 4. Dibujar nodos con sprites de glow precomputados
        # Ordenamos de atrás hacia adelante para composición correcta de resplandor
        order = np.argsort(z_depths)  # Menor Z primero (fondo), mayor Z después (frente)
        glow_pixmap = self.glow_sprites["cyan"]
        glow_orig_size = glow_pixmap.width()

        for idx in order:
            x, y = coords_2d[idx]
            z = z_depths[idx]
            norm_z = float(np.clip((z - min_z) / (max_z - min_z + 1e-5), 0.0, 1.0))

            # Escala del sprite por perspectiva y profundidad
            sprite_scale = 0.45 + norm_z * 0.55
            draw_size = glow_orig_size * sprite_scale
            half_size = draw_size * 0.5

            dest_rect = QRectF(x - half_size, y - half_size, draw_size, draw_size)
            painter.setOpacity(0.35 + norm_z * 0.65)
            painter.drawPixmap(dest_rect, glow_pixmap, QRectF(glow_pixmap.rect()))

            # Núcleo brillante en el centro del nodo
            core_radius = 1.0 + norm_z * 1.8
            c_color = QColor(self.color_core)
            c_color.setAlpha(int(80 + norm_z * 175))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c_color)
            painter.drawEllipse(QPointF(x, y), core_radius, core_radius)

        painter.setOpacity(1.0)
        painter.end()
