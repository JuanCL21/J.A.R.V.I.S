"""
JARVIS — Sistema de Diseño y Tema Centralizado (PyQt6).
Extraído y adaptado fielmente del proyecto de Stitch 'JARVIS Local Desktop Interface'.

Provee:
- Constantes canónicas de color (Tonal Foundation, Accents, Text Hierarchy, Borders).
- Escala de espaciado y radios de borde.
- Carga e inicialización embebida de fuentes ('IBM Plex Sans' e 'IBM Plex Mono').
- Generador de QSS global (build_global_qss()) y estilos de componentes reutilizables.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QColor, QFont, QFontDatabase


# ==============================================================================
# 1. PALETA DE COLORES EXACTA (Stitch Design System)
# ==============================================================================
class Colors:
    # --- Tonal Foundation (Superficies y Fondos) ---
    CANVAS_BASE = "#121417"          # Fondo raíz y marcos principales de la ventana
    SURFACE_DIM = "#111316"          # Fondo profundo atenuado
    SURFACE_1 = "#1A1D21"            # Nivel 1: Paneles principales, viewport de chat, contenido
    SURFACE_2 = "#22262B"            # Nivel 2: Barra lateral, tarjetas elevadas, contenedores de inputs
    SURFACE_3 = "#2A2F36"            # Nivel 3: Estados hover, bloques de código anidados, pills activos
    SURFACE_BRIGHT = "#37393D"       # Superficie iluminada / resaltados sutiles
    SURFACE_LOWEST = "#0C0E11"       # Contenedor más bajo (cajas de terminal)
    SURFACE_CONTAINER = "#1E2023"    # Contenedor genérico
    SURFACE_CONTAINER_HIGH = "#282A2D"

    # --- Jerarquía de Bordes y Separadores ---
    BORDER_STRUCTURAL = "#2D3239"    # Borde estructural unificado (paneles, tarjetas, divisores)
    BORDER_SUBTLE = "#1F2328"        # Borde sutil interno e inactivo
    BORDER_HOVER = "#3E4850"         # Borde en estado hover
    OUTLINE = "#88929B"              # Delineado de contraste

    # --- Jerarquía Tipográfica y Glifos ---
    TEXT_HIGH = "#F1F5F9"            # Alto énfasis: Entradas de usuario, respuestas, títulos
    TEXT_MEDIUM = "#94A3B8"          # Medio énfasis: Metadatos, etiquetas, descripciones, tooltips
    TEXT_LOW = "#64748B"             # Bajo énfasis: Placeholders, atajos, glifos inactivos
    TEXT_ON_SURFACE = "#E2E2E6"
    TEXT_MUTED = "#526071"

    # --- Disciplina de Acentos y Estados Semánticos ---
    PRIMARY = "#0EA5E9"              # Acento principal: Foco, cursor de streaming, botones primarios
    PRIMARY_BRIGHT = "#89CEFF"       # Cian brillante para glows y badges
    PRIMARY_CONTAINER = "#003751"    # Fondo contenedor de acento primario
    PRIMARY_HOVER = "#38BDF8"        # Hover sobre acento primario

    SECONDARY = "#14B8A6"            # Acento secundario (Teal): Estado listo, telemetría verificada
    SECONDARY_CONTAINER = "#003F38"
    SECONDARY_HOVER = "#2DD4BF"

    WARNING = "#F59E0B"              # Advertencia (Ámbar): Límites de contexto, throttling, modo sin verificar
    WARNING_CONTAINER = "#451A03"
    WARNING_HOVER = "#FBBF24"

    ERROR = "#EF4444"                # Error / Crítico (Rojo): Fallos de ejecución, violaciones de sandbox
    ERROR_CONTAINER = "#450A0A"
    ERROR_HOVER = "#F87171"

    SUCCESS = "#10B981"              # Éxito (Esmeralda/Verde): Acciones confirmadas, plugins curados
    SUCCESS_CONTAINER = "#064E3B"


# ==============================================================================
# 2. ESPACIADO Y RADIOS DE BORDE (Stitch Spacing Scale & Shapes)
# ==============================================================================
class Spacing:
    SPACE_2XS = 2
    SPACE_XS = 4
    SPACE_SM = 8
    SPACE_MD = 12
    SPACE_BASE = 16
    SPACE_LG = 20
    SPACE_XL = 24
    SPACE_2XL = 32
    SPACE_3XL = 40

    SIDEBAR_WIDTH = 256
    SIDEBAR_COLLAPSED = 56
    SIDECAR_WIDTH = 320
    PROMPT_MAX_WIDTH = 768


class Radius:
    XS = 2
    SM = 4          # Botones estándar, inputs, celdas de tabla
    MD = 6          # Contenedores medianos, tags
    LG = 8          # Tarjetas principales, bloques de código
    XL = 12         # Diálogos modales, popovers flotantes
    FULL = 9999     # Pills, chips de estado, badges circulares


# ==============================================================================
# 3. GESTIÓN Y EMBEBIDO DE FUENTES (IBM Plex Sans & IBM Plex Mono)
# ==============================================================================
class Typography:
    FONT_FAMILY_GENERAL = "IBM Plex Sans"
    FONT_FAMILY_MONO = "IBM Plex Mono"

    _FONTS_INITIALIZED = False

    @classmethod
    def initialize_fonts(cls) -> bool:
        """
        Embebe todas las variantes de IBM Plex Sans e IBM Plex Mono en QFontDatabase
        desde la carpeta local ui/assets/fonts/ para garantizar independencia del SO.
        """
        if cls._FONTS_INITIALIZED:
            return True

        fonts_dir = Path(__file__).resolve().parent / "assets" / "fonts"
        if not fonts_dir.exists():
            return False

        font_files = [
            "IBMPlexSans-Regular.ttf",
            "IBMPlexSans-Medium.ttf",
            "IBMPlexSans-SemiBold.ttf",
            "IBMPlexSans-Bold.ttf",
            "IBMPlexMono-Regular.ttf",
            "IBMPlexMono-Medium.ttf",
            "IBMPlexMono-SemiBold.ttf",
            "IBMPlexMono-Bold.ttf",
        ]

        loaded_any = False
        for f in font_files:
            font_path = str(fonts_dir / f)
            if os.path.isfile(font_path):
                fid = QFontDatabase.addApplicationFont(font_path)
                if fid != -1:
                    loaded_any = True

        cls._FONTS_INITIALIZED = loaded_any
        return loaded_any

    @classmethod
    def get_font(
        cls,
        mono: bool = False,
        size_pt: int = 10,
        weight: QFont.Weight = QFont.Weight.Normal,
    ) -> QFont:
        """Retorna una instancia de QFont con la tipografía oficial del proyecto."""
        cls.initialize_fonts()
        family = cls.FONT_FAMILY_MONO if mono else cls.FONT_FAMILY_GENERAL
        font = QFont(family, size_pt)
        font.setWeight(weight)
        return font


# ==============================================================================
# 4. HOJA DE ESTILOS GLOBAL (QSS)
# ==============================================================================
def build_global_qss() -> str:
    """
    Genera la hoja de estilos global QSS para QApplication/QMainWindow,
    inyectando los tokens canónicos de diseño.
    """
    return f"""
    /* === ESTILOS GLOBALES BASE === */
    QWidget {{
        background-color: {Colors.CANVAS_BASE};
        color: {Colors.TEXT_HIGH};
        font-family: '{Typography.FONT_FAMILY_GENERAL}', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 13px;
        selection-background-color: {Colors.PRIMARY};
        selection-color: {Colors.CANVAS_BASE};
    }}

    QMainWindow, QDialog {{
        background-color: {Colors.CANVAS_BASE};
    }}

    /* === FRAMES Y CONTENEDORES === */
    QFrame#surface_1 {{
        background-color: {Colors.SURFACE_1};
        border: 1px solid {Colors.BORDER_STRUCTURAL};
        border-radius: {Radius.LG}px;
    }}

    QFrame#surface_2 {{
        background-color: {Colors.SURFACE_2};
        border: 1px solid {Colors.BORDER_STRUCTURAL};
        border-radius: {Radius.LG}px;
    }}

    QFrame#surface_card {{
        background-color: {Colors.SURFACE_1};
        border: 1px solid {Colors.BORDER_STRUCTURAL};
        border-radius: {Radius.LG}px;
    }}
    QFrame#surface_card:hover {{
        border: 1px solid {Colors.BORDER_HOVER};
        background-color: {Colors.SURFACE_2};
    }}

    /* === BOTONES (Buttons) === */
    /* Botón Primario */
    QPushButton#btn_primary {{
        background-color: {Colors.PRIMARY};
        color: {Colors.CANVAS_BASE};
        border: none;
        border-radius: {Radius.SM}px;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton#btn_primary:hover {{
        background-color: {Colors.PRIMARY_HOVER};
    }}
    QPushButton#btn_primary:pressed {{
        background-color: {Colors.PRIMARY};
    }}
    QPushButton#btn_primary:disabled {{
        background-color: {Colors.SURFACE_3};
        color: {Colors.TEXT_LOW};
    }}

    /* Botón Secundario / Ghost */
    QPushButton, QPushButton#btn_secondary {{
        background-color: transparent;
        color: {Colors.TEXT_MEDIUM};
        border: 1px solid {Colors.BORDER_STRUCTURAL};
        border-radius: {Radius.SM}px;
        padding: 8px 14px;
        font-weight: 500;
        font-size: 12px;
    }}
    QPushButton:hover, QPushButton#btn_secondary:hover {{
        background-color: {Colors.SURFACE_2};
        color: {Colors.TEXT_HIGH};
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QPushButton:pressed, QPushButton#btn_secondary:pressed {{
        background-color: {Colors.SURFACE_3};
    }}
    QPushButton:disabled, QPushButton#btn_secondary:disabled {{
        border-color: {Colors.BORDER_SUBTLE};
        color: {Colors.TEXT_LOW};
    }}

    /* Botón de Peligro / Advertencia */
    QPushButton#btn_danger {{
        background-color: rgba(239, 68, 68, 0.15);
        color: {Colors.ERROR};
        border: 1px solid {Colors.ERROR};
        border-radius: {Radius.SM}px;
        padding: 8px 14px;
        font-weight: 600;
    }}
    QPushButton#btn_danger:hover {{
        background-color: rgba(239, 68, 68, 0.3);
        color: #ffffff;
    }}

    /* Botón de Advertencia (Ámbar) */
    QPushButton#btn_warning {{
        background-color: rgba(245, 158, 11, 0.15);
        color: {Colors.WARNING};
        border: 1px solid {Colors.WARNING};
        border-radius: {Radius.SM}px;
        padding: 8px 14px;
        font-weight: 600;
    }}
    QPushButton#btn_warning:hover {{
        background-color: rgba(245, 158, 11, 0.3);
        color: #ffffff;
    }}

    /* === ENTRADAS DE TEXTO (Inputs) === */
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {Colors.SURFACE_2};
        border: 1px solid {Colors.BORDER_STRUCTURAL};
        border-radius: {Radius.SM}px;
        color: {Colors.TEXT_HIGH};
        padding: 8px 12px;
        font-size: 13px;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {Colors.PRIMARY};
        background-color: {Colors.SURFACE_2};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
        background-color: {Colors.SURFACE_DIM};
        color: {Colors.TEXT_LOW};
        border-color: {Colors.BORDER_SUBTLE};
    }}

    /* === SCROLLBARS MINIMALISTAS === */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {Colors.BORDER_STRUCTURAL};
        min-height: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {Colors.BORDER_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {Colors.BORDER_STRUCTURAL};
        min-width: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {Colors.BORDER_HOVER};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* === LISTAS, TABLAS Y ÁRBOLES === */
    QListWidget, QTableWidget, QTreeWidget {{
        background-color: {Colors.SURFACE_1};
        border: 1px solid {Colors.BORDER_STRUCTURAL};
        border-radius: {Radius.LG}px;
        gridline-color: {Colors.BORDER_SUBTLE};
        outline: none;
    }}
    QListWidget::item, QTableWidget::item {{
        padding: 8px 10px;
        border-radius: {Radius.SM}px;
        color: {Colors.TEXT_HIGH};
    }}
    QListWidget::item:hover, QTableWidget::item:hover {{
        background-color: {Colors.SURFACE_2};
    }}
    QListWidget::item:selected, QTableWidget::item:selected {{
        background-color: {Colors.SURFACE_3};
        color: {Colors.TEXT_HIGH};
        border-left: 2px solid {Colors.PRIMARY};
    }}

    QHeaderView::section {{
        background-color: {Colors.SURFACE_2};
        color: {Colors.TEXT_MEDIUM};
        padding: 6px 10px;
        border: none;
        border-bottom: 1px solid {Colors.BORDER_STRUCTURAL};
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* === LABELS DE MONOSPACE Y METADATOS === */
    QLabel#lbl_mono {{
        font-family: '{Typography.FONT_FAMILY_MONO}', monospace;
        color: {Colors.TEXT_MEDIUM};
        font-size: 12px;
    }}

    QLabel#lbl_title {{
        color: {Colors.TEXT_HIGH};
        font-size: 16px;
        font-weight: 600;
    }}

    QLabel#lbl_subtitle {{
        color: {Colors.TEXT_MEDIUM};
        font-size: 12px;
    }}

    /* === STATUS PILLS / BADGES === */
    QLabel#pill_ready {{
        background-color: rgba(20, 184, 166, 0.15);
        color: {Colors.SECONDARY};
        border: 1px solid rgba(20, 184, 166, 0.35);
        border-radius: {Radius.FULL}px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#pill_busy {{
        background-color: rgba(14, 165, 233, 0.15);
        color: {Colors.PRIMARY};
        border: 1px solid rgba(14, 165, 233, 0.35);
        border-radius: {Radius.FULL}px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#pill_warning {{
        background-color: rgba(245, 158, 11, 0.15);
        color: {Colors.WARNING};
        border: 1px solid rgba(245, 158, 11, 0.35);
        border-radius: {Radius.FULL}px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#pill_error {{
        background-color: rgba(239, 68, 68, 0.15);
        color: {Colors.ERROR};
        border: 1px solid rgba(239, 68, 68, 0.35);
        border-radius: {Radius.FULL}px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
    }}

    /* === TOOLTIPS === */
    QToolTip {{
        background-color: {Colors.SURFACE_3};
        color: {Colors.TEXT_HIGH};
        border: 1px solid {Colors.BORDER_STRUCTURAL};
        border-radius: {Radius.SM}px;
        padding: 6px 10px;
        font-size: 11px;
    }}
    """
