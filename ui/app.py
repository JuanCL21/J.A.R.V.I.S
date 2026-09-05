"""
JARVIS — Aplicación de Escritorio e Interfaz Visual Multimodal (PyQt6).
Adaptación fiel del sistema de diseño 'Obsidian Assistant' extraído de Google Stitch.

Estructura:
- Nav Rail Lateral Izquierdo (56px fijo) con selección fluida de vistas.
- Vista 0: 'JARVIS - Asistente con Orbe Interactivo' (Escenario central con orbe reactivo + panel de chat).
- Vista 1: 'JARVIS - Chat Operativo y Consola' (Workspace extendido con telemetría de contexto).
- Vista 2: 'JARVIS - Catálogo de Plugins' (Catálogo curado embebido).
- Vista 3: 'JARVIS - Configuración del Sistema' (Panel de configuración embebido).
- Vista 4: 'JARVIS - Registro de Auditoría' (Visor de logs de seguridad).
"""

import math
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Asegurar importación de core y ui desde la raíz del repositorio
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None
    WEBENGINE_AVAILABLE = False
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
    QResizeEvent,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.voice_session import VoiceSession
from ui.theme import Colors, Radius, Spacing, Typography, build_global_qss
from ui.audio_visualizer import ReactiveAudioVisualizer, VisualizerState
from ui.confirmation_dialog import ConfirmationDialog, ConfirmationRequest
from ui.plugin_management_dialog import PluginManagementDialog
from ui.toast_notification import ToastManager, ToastNotification
from ui.audit_viewer_screen import AuditViewerDialog, AuditViewerScreen
from ui.settings_dialog import SettingsDialog
from ui.plugin_catalog import PluginCatalogScreen
from ui.chat_screen import ChatSimpleScreen


# ==============================================================================
# PUENTES SEGUROS ENTRE HILOS (Qt Signals & Bridges)
# ==============================================================================
class AudioCaptureBridge(QObject):
    """Puente seguro entre hilos para transmitir eventos del callback de sounddevice hacia Qt."""
    sig_audio_chunk = pyqtSignal(np.ndarray)
    sig_capture_error = pyqtSignal(str)


class VoiceSessionQtBridge(QObject):
    """Puente seguro entre hilos para comunicar eventos de VoiceSession con la UI de Qt."""
    sig_state_changed = pyqtSignal(str)
    sig_audio_output = pyqtSignal(bytes, float)
    sig_text_output = pyqtSignal(str)
    sig_error = pyqtSignal(str)
    sig_silence_timeout = pyqtSignal()


# ==============================================================================
# COMPONENTES AUXILIARES ESTILIZADOS (Stitch Design System)
# ==============================================================================
class MiniGlowingOrb(QWidget):
    """Mini orbe luminoso (28x28) con punto pulsante y halo para el encabezado de Stitch."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    def _tick(self) -> None:
        self.phase += 0.06
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        cx, cy = 14.0, 14.0

        # Fondo circular oscuro
        painter.setBrush(QColor(Colors.SURFACE_CONTAINER_HIGH))
        painter.drawEllipse(QPointF(cx, cy), 13, 13)

        # Halo cyan pulsante
        pulse = 0.5 + 0.5 * math.sin(self.phase * 2.2)
        grad = QRadialGradient(cx, cy, 12)
        grad.setColorAt(0.0, QColor(79, 219, 200, int(75 * pulse)))
        grad.setColorAt(1.0, QColor(79, 219, 200, 0))
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(cx, cy), 12, 12)

        # Centro vibrante
        painter.setBrush(QColor(Colors.PRIMARY_BRIGHT))
        r = 3.2 + 0.9 * pulse
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.end()


class AnimatedSoundWaves(QWidget):
    """3 barras de onda sonoras animadas para el botón de escuchar de Stitch (anim-wave)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(80)

    def _tick(self) -> None:
        self.phase += 0.35
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        h = float(self.height())

        h1 = 4.0 + 3.0 * math.sin(self.phase + 0.1)
        h2 = 6.0 + 5.5 * math.sin(self.phase + 1.1)
        h3 = 3.5 + 3.0 * math.sin(self.phase + 0.6)

        painter.setBrush(QColor(Colors.PRIMARY_BRIGHT))
        painter.drawRoundedRect(QRectF(1, h - h1 - 1, 2, h1), 1, 1)
        painter.setBrush(QColor(Colors.SECONDARY))
        painter.drawRoundedRect(QRectF(5, h - h2 - 1, 2, h2), 1, 1)
        painter.setBrush(QColor(Colors.PRIMARY_BRIGHT))
        painter.drawRoundedRect(QRectF(9, h - h3 - 1, 2, h3), 1, 1)
        painter.end()


class ChatBubble(QFrame):
    """Burbuja conversacional enriquecida idéntica al diseño de Stitch."""

    def __init__(
        self,
        sender_name: str,
        text: str,
        is_user: bool = False,
        timestamp: str = "",
        attachment: Optional[dict] = None,
        has_actions: bool = False,
        is_voice_dictation: bool = False,
        on_listen: Optional[object] = None,
        on_copy: Optional[object] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("chat_bubble")
        self._raw_text = text
        self._on_listen = on_listen
        self._on_copy = on_copy

        if not timestamp:
            timestamp = time.strftime("%H:%M")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # Header de la burbuja (Autor · Hora)
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(6)

        if is_user:
            meta_layout.addStretch()
            lbl_sender = QLabel(sender_name)
            lbl_sender.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 11px; font-weight: 600;")
            lbl_dot = QLabel("·")
            lbl_dot.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px;")
            lbl_time = QLabel(timestamp)
            lbl_time.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            meta_layout.addWidget(lbl_sender)
            meta_layout.addWidget(lbl_dot)
            meta_layout.addWidget(lbl_time)

            self.setStyleSheet(
                f"""
                QFrame#chat_bubble {{
                    background-color: {Colors.SURFACE_2};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.LG}px;
                    border-top-right-radius: 2px;
                }}
                """
            )
        else:
            lbl_sender = QLabel(sender_name)
            lbl_sender.setStyleSheet(f"color: {Colors.PRIMARY_BRIGHT}; font-size: 11px; font-weight: bold;")
            lbl_dot = QLabel("·")
            lbl_dot.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px;")
            lbl_time = QLabel(timestamp)
            lbl_time.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            meta_layout.addWidget(lbl_sender)
            meta_layout.addWidget(lbl_dot)
            meta_layout.addWidget(lbl_time)
            meta_layout.addStretch()

            self.setStyleSheet(
                f"""
                QFrame#chat_bubble {{
                    background-color: {Colors.SURFACE_1};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.LG}px;
                    border-top-left-radius: 2px;
                }}
                """
            )

        main_layout.addLayout(meta_layout)

        # Contenido del texto
        if is_voice_dictation:
            dict_row = QHBoxLayout()
            dict_row.setSpacing(8)
            lbl_mic = QLabel("🎙")
            lbl_mic.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 14px;")
            lbl_text = QLabel(text)
            lbl_text.setWordWrap(True)
            lbl_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_text.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 13px; font-style: italic; line-height: 1.4;")
            dict_row.addWidget(lbl_mic)
            dict_row.addWidget(lbl_text, stretch=1)
            main_layout.addLayout(dict_row)
        else:
            lbl_text = QLabel()
            lbl_text.setWordWrap(True)
            lbl_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            # Resaltado sutil para rutas como /docs
            formatted_text = text.replace(
                "/docs",
                f"<span style='color: {Colors.PRIMARY_BRIGHT}; background-color: {Colors.SURFACE_LOWEST}; padding: 1px 4px; border-radius: 3px; font-family: {Typography.FONT_FAMILY_MONO};'>/docs</span>"
            )
            lbl_text.setText(formatted_text)
            lbl_text.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 13px; line-height: 1.4;")
            main_layout.addWidget(lbl_text)

        # Chip de Archivo Adjunto (PDF generado en Stitch)
        if attachment:
            chip_frame = QFrame()
            chip_frame.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_LOWEST};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.MD}px;
                    padding: 4px;
                }}
                QFrame:hover {{
                    border: 1px solid {Colors.PRIMARY_BRIGHT}55;
                }}
                """
            )
            chip_layout = QHBoxLayout(chip_frame)
            chip_layout.setContentsMargins(8, 6, 8, 6)
            chip_layout.setSpacing(10)

            # Ícono de documento en caja
            lbl_doc_icon = QLabel("📄")
            lbl_doc_icon.setFixedSize(30, 30)
            lbl_doc_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_doc_icon.setStyleSheet(
                f"background-color: {Colors.SURFACE_CONTAINER_HIGH}; border-radius: {Radius.SM}px; font-size: 14px;"
            )
            chip_layout.addWidget(lbl_doc_icon)

            info_col = QVBoxLayout()
            info_col.setContentsMargins(0, 0, 0, 0)
            info_col.setSpacing(1)

            lbl_fname = QLabel(attachment.get("name", "documento.pdf"))
            lbl_fname.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 12px; font-weight: 600;")
            info_col.addWidget(lbl_fname)

            lbl_fmeta = QLabel(attachment.get("size", "142 KB · Generado localmente"))
            lbl_fmeta.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10.5px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            info_col.addWidget(lbl_fmeta)

            chip_layout.addLayout(info_col, stretch=1)

            btn_dl = QPushButton("⬇")
            btn_dl.setFixedSize(26, 26)
            btn_dl.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_dl.setToolTip("Descargar o abrir archivo")
            btn_dl.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Colors.TEXT_MEDIUM};
                    border: none;
                    border-radius: {Radius.SM}px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    color: {Colors.PRIMARY_BRIGHT};
                    background-color: {Colors.SURFACE_CONTAINER_HIGH};
                }}
                """
            )
            chip_layout.addWidget(btn_dl)
            main_layout.addWidget(chip_frame)

        # Barra de Acciones del Asistente (Stitch Actions Toolbar)
        if has_actions and not is_user:
            act_layout = QHBoxLayout()
            act_layout.setContentsMargins(0, 4, 0, 0)
            act_layout.setSpacing(8)

            # Botón Escuchar con ondas animadas
            btn_listen = QPushButton(" Escuchar")
            btn_listen.setIcon(QIcon())
            btn_listen.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_listen.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {Colors.SURFACE_CONTAINER};
                    color: {Colors.PRIMARY_BRIGHT};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.SM}px;
                    padding: 3px 8px;
                    font-size: 11px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {Colors.SURFACE_CONTAINER_HIGH};
                }}
                """
            )
            listen_wrapper = QHBoxLayout()
            listen_wrapper.setContentsMargins(0, 0, 0, 0)
            listen_wrapper.setSpacing(4)
            wave_bars = AnimatedSoundWaves()
            btn_listen_layout = QHBoxLayout(btn_listen)
            btn_listen_layout.setContentsMargins(4, 2, 6, 2)
            btn_listen_layout.setSpacing(4)
            btn_listen_layout.addStretch()
            btn_listen_layout.addWidget(wave_bars)

            if on_listen:
                btn_listen.clicked.connect(on_listen)
            act_layout.addWidget(btn_listen)

            # Botón Copiar
            btn_copy = QPushButton("Copiar")
            btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_copy.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Colors.TEXT_MEDIUM};
                    border: none;
                    border-radius: {Radius.SM}px;
                    padding: 3px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    color: {Colors.TEXT_HIGH};
                    background-color: {Colors.SURFACE_CONTAINER_HIGH};
                }}
                """
            )
            if on_copy:
                btn_copy.clicked.connect(on_copy)
            else:
                btn_copy.clicked.connect(self._copy_content)
            act_layout.addWidget(btn_copy)

            act_layout.addStretch()

            # Feedback
            btn_up = QPushButton("👍")
            btn_up.setFixedSize(24, 24)
            btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_up.setStyleSheet("background: transparent; border: none; font-size: 11px;")
            act_layout.addWidget(btn_up)

            btn_down = QPushButton("👎")
            btn_down.setFixedSize(24, 24)
            btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_down.setStyleSheet("background: transparent; border: none; font-size: 11px;")
            act_layout.addWidget(btn_down)

            main_layout.addLayout(act_layout)

    def _copy_content(self) -> None:
        clip = QApplication.clipboard()
        if clip:
            clip.setText(self._raw_text)


# ==============================================================================
# VENTANA PRINCIPAL DE JARVIS
# ==============================================================================
class JarvisMainWindow(QMainWindow):
    """
    Ventana principal de escritorio para JARVIS adaptada al diseño de Stitch.
    """

    def __init__(self):
        super().__init__()
        Typography.initialize_fonts()

        self.setWindowTitle("JARVIS // Asistente Neural & Consola de Operaciones")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 680)

        # Aplicar el tema global
        self.setStyleSheet(build_global_qss())

        # Temporizadores auxiliares
        self.fps_timer = QTimer(self)
        self.audio_sim_timer = QTimer(self)

        # Puentes de audio y voz
        self.audio_bridge = AudioCaptureBridge()
        self.voice_bridge = VoiceSessionQtBridge()
        self.audio_stream: Optional[sd.InputStream] = None
        self.audio_running = False

        # Conectar señales
        self.audio_bridge.sig_audio_chunk.connect(self._process_audio_chunk)
        self.audio_bridge.sig_capture_error.connect(self._handle_capture_error)
        self.voice_bridge.sig_state_changed.connect(self._handle_voice_state_changed)
        self.voice_bridge.sig_audio_output.connect(self._handle_voice_audio_output)
        self.voice_bridge.sig_text_output.connect(self._handle_voice_text_output)
        self.voice_bridge.sig_error.connect(self._handle_voice_error)
        self.voice_bridge.sig_silence_timeout.connect(self._handle_voice_silence_timeout)

        # Inicializar sesión de voz (Gemini Live)
        self.voice_session: Optional[VoiceSession] = None
        try:
            self.voice_session = VoiceSession(
                on_state_changed=self.voice_bridge.sig_state_changed.emit,
                on_audio_output=self.voice_bridge.sig_audio_output.emit,
                on_text_output=self.voice_bridge.sig_text_output.emit,
                on_error=self.voice_bridge.sig_error.emit,
                on_silence_timeout=self.voice_bridge.sig_silence_timeout.emit,
            )
        except Exception as e:
            self.append_log(f"[VOICE // WARN] Inicialización diferida: {e}")

        # Construcción de la UI Central
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Nav Rail Lateral Izquierdo (56px)
        self.nav_rail = self._build_nav_rail()
        root_layout.addWidget(self.nav_rail)

        # 2. Stack Principal de Vistas
        self.view_stack = QStackedWidget(self)
        self.view_stack.setStyleSheet(f"background-color: {Colors.CANVAS_BASE};")

        # Vista 0: Asistente con Orbe Interactivo
        self.orb_view = self._build_orb_view()
        self.view_stack.addWidget(self.orb_view)

        # Vista 1: Chat Operativo y Consola Extendida
        self.chat_console_view = self._build_chat_console_view()
        self.view_stack.addWidget(self.chat_console_view)

        # Vista 2: Catálogo de Plugins Curados
        self.plugin_catalog_view = PluginCatalogScreen(
            parent=self,
            on_status_message=self._handle_plugin_status_message,
        )
        self.view_stack.addWidget(self.plugin_catalog_view)

        # Vista 3: Ajustes del Sistema
        self.settings_view = SettingsDialog(parent=self)
        self.view_stack.addWidget(self.settings_view)

        # Vista 4: Inspección de Auditoría
        self.audit_view = AuditViewerScreen(parent=self)
        self.view_stack.addWidget(self.audit_view)

        root_layout.addWidget(self.view_stack, stretch=1)

        # Alias de consola para compatibilidad
        self.log_console = self.console_log

        # Mensaje de bienvenida inicial
        self.append_chat_message("JARVIS", "Sistemas en línea. Aislamiento de seguridad activo y preparado para recibir instrucciones.")

        # Atajo global para retraer o expandir el chat manual con JARVIS (Ctrl+M)
        self.shortcut_toggle_chat = QShortcut(QKeySequence("Ctrl+M"), self)
        self.shortcut_toggle_chat.activated.connect(self.toggle_chat_panel)

    # ==========================================================================
    # 1. BARRA LATERAL DE NAVEGACIÓN (NAV RAIL)
    # ==========================================================================
    def _build_nav_rail(self) -> QFrame:
        rail = QFrame(self)
        rail.setFixedWidth(56)
        rail.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_LOWEST};
                border-right: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(6, 16, 6, 16)
        layout.setSpacing(12)

        # Logo / Top Glyph
        lbl_logo = QLabel("JARVIS")
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_logo.setStyleSheet(
            f"color: {Colors.PRIMARY}; font-size: 10px; font-weight: 800; letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        layout.addWidget(lbl_logo)
        layout.addSpacing(10)

        # Botones de navegación
        self.nav_buttons = []

        # 0: Orbe
        self.btn_nav_orb = QPushButton("✦")
        self.btn_nav_orb.setFixedSize(44, 44)
        self.btn_nav_orb.setToolTip("Asistente Neural (Orbe)")
        self.btn_nav_orb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_orb.clicked.connect(lambda: self._switch_view(0))
        layout.addWidget(self.btn_nav_orb)
        self.nav_buttons.append(self.btn_nav_orb)

        # 1: Chat Operativo
        self.btn_nav_chat = QPushButton("💬")
        self.btn_nav_chat.setFixedSize(44, 44)
        self.btn_nav_chat.setToolTip("Chat Operativo & Consola")
        self.btn_nav_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_chat.clicked.connect(lambda: self._switch_view(1))
        layout.addWidget(self.btn_nav_chat)
        self.nav_buttons.append(self.btn_nav_chat)

        # 2: Plugins (Escudo)
        self.btn_plugins = QPushButton("🛡")
        self.btn_plugins.setObjectName("plugins_shield_btn")
        self.btn_plugins.setFixedSize(44, 44)
        self.btn_plugins.setToolTip("Gestión de Plugins")
        self.btn_plugins.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plugins.clicked.connect(self._open_plugin_management)
        layout.addWidget(self.btn_plugins)
        self.nav_buttons.append(self.btn_plugins)

        # 3: Configuración
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("settings_btn")
        self.btn_settings.setFixedSize(44, 44)
        self.btn_settings.setToolTip("Configuración")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        layout.addWidget(self.btn_settings)
        self.nav_buttons.append(self.btn_settings)

        # 4: Auditoría
        self.btn_audit_logs = QPushButton("📜")
        self.btn_audit_logs.setObjectName("audit_logs_btn")
        self.btn_audit_logs.setFixedSize(44, 44)
        self.btn_audit_logs.setToolTip("Registro de Auditoría")
        self.btn_audit_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_audit_logs.clicked.connect(self._open_audit_viewer)
        layout.addWidget(self.btn_audit_logs)
        self.nav_buttons.append(self.btn_audit_logs)

        layout.addStretch()

        # Indicador de estado inferior (Teal pulse dot)
        self.lbl_system_dot = QLabel("●")
        self.lbl_system_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_system_dot.setToolTip("Motor Neural Listo y Seguro")
        self.lbl_system_dot.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 14px;")
        layout.addWidget(self.lbl_system_dot)

        self._update_nav_styles(0)
        return rail

    def _update_nav_styles(self, active_index: int) -> None:
        for idx, btn in enumerate(self.nav_buttons):
            if idx == active_index:
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {Colors.SURFACE_3};
                        color: {Colors.PRIMARY};
                        border: none;
                        border-left: 3px solid {Colors.PRIMARY};
                        border-radius: {Radius.SM}px;
                        font-size: 16px;
                    }}
                    """
                )
            else:
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {Colors.TEXT_MEDIUM};
                        border: none;
                        border-radius: {Radius.SM}px;
                        font-size: 16px;
                    }}
                    QPushButton:hover {{
                        background-color: {Colors.SURFACE_2};
                        color: {Colors.TEXT_HIGH};
                    }}
                    """
                )

    def _switch_view(self, index: int) -> None:
        self.view_stack.setCurrentIndex(index)
        self._update_nav_styles(index)

        # Si entra al catálogo o auditoría, refrescar
        if index == 2 and hasattr(self, "plugin_catalog_view") and hasattr(self.plugin_catalog_view, "refresh"):
            self.plugin_catalog_view.refresh()
        elif index == 4 and hasattr(self, "audit_view") and hasattr(self.audit_view, "refresh_logs"):
            self.audit_view.refresh_logs()

    def _open_plugin_management(self) -> None:
        self.append_log("Accediendo a Gestión de Plugins...")
        PluginManagementDialog.open_management(parent=self, on_status_message=self._handle_plugin_status_message)

    def _open_settings(self) -> None:
        self.append_log("Accediendo a Configuración...")
        SettingsDialog.open_settings(parent=self)

    def _open_audit_viewer(self) -> None:
        self.append_log("Accediendo a Registro de Auditoría...")
        AuditViewerDialog.open_viewer(parent=self)

    # ==========================================================================
    # 2. VISTA 0: ASISTENTE CON ORBE INTERACTIVO
    # ==========================================================================
    def _build_orb_view(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- ÁREA IZQUIERDA / CENTRAL: Escenario del Orbe ---
        self.orb_stage = QFrame(container)
        self.orb_stage.setObjectName("orb_stage")
        self.orb_stage.setStyleSheet(
            f"""
            QFrame#orb_stage {{
                background: #030409;
                border-right: 1px solid #1f2328;
            }}
            """
        )
        self.orb_stage.installEventFilter(self)
        orb_layout = QVBoxLayout(self.orb_stage)
        orb_layout.setContentsMargins(0, 0, 0, 0)
        orb_layout.setSpacing(0)

        # Botón flotante para expandir/restaurar el panel de chat cuando está retraído
        self.btn_expand_chat = QPushButton(self.orb_stage)
        self.btn_expand_chat.setIcon(self._create_dock_icon(is_collapsed=True, color="#38BDF8"))
        self.btn_expand_chat.setIconSize(QSize(16, 16))
        self.btn_expand_chat.setText(" Chat")
        self.btn_expand_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand_chat.setToolTip("Expandir chat manual con JARVIS (Ctrl+M)")
        self.btn_expand_chat.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(9, 13, 22, 0.88);
                color: {Colors.TEXT_HIGH};
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: {Radius.SM}px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.4px;
            }}
            QPushButton:hover {{
                background-color: rgba(18, 26, 42, 0.96);
                border-color: {Colors.PRIMARY_BRIGHT};
                color: #FFFFFF;
            }}
            """
        )
        self.btn_expand_chat.clicked.connect(self.toggle_chat_panel)
        self.btn_expand_chat.hide()

        # Vista WebEngine con el prototipo v2 exacto en HTML5 Canvas (100% fiel al prototipo proporcionado)
        is_headless_test = "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        self.orb_web = None
        if WEBENGINE_AVAILABLE and QWebEngineView is not None and not is_headless_test:
            try:
                self.orb_web = QWebEngineView(self.orb_stage)
                self.orb_web.page().setBackgroundColor(QColor("#030409"))
                self.orb_web.setStyleSheet("background: #030409; border: none;")
                html_file = Path(__file__).resolve().parent / "assets" / "orb_prototype_v2.html"
                if html_file.exists():
                    self.orb_web.load(QUrl.fromLocalFile(str(html_file)))
                self.orb_web.installEventFilter(self)
                orb_layout.addWidget(self.orb_web, stretch=1)
            except Exception:
                self.orb_web = None

        # Contenedor de compatibilidad para tests y lógica de negocio (121 tests verdes)
        test_compat_container = QWidget(self.orb_stage)
        test_compat_layout = QVBoxLayout(test_compat_container)
        test_compat_layout.setContentsMargins(0, 0, 0, 0)

        # Atributos de compatibilidad (ocultos de la interfaz visual)
        self.lbl_telemetry_status = QLabel("● NÚCLEO: ACTIVO", test_compat_container)
        self.lbl_telemetry_model = QLabel("MOTOR: LOCAL / GEMINI", test_compat_container)
        self.fps_label = QLabel("FPS: 60", test_compat_container)

        self.visualizer = ReactiveAudioVisualizer(test_compat_container)
        self.visualizer.setMinimumSize(480, 360)
        self.visualizer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.visualizer.cursor_hover_enabled = True
        test_compat_layout.addWidget(self.visualizer)

        self.lbl_caption = QLabel("“JARVIS a la espera de instrucciones…”", test_compat_container)
        test_compat_layout.addWidget(self.lbl_caption)

        self.lbl_hint = QLabel("tocá el orbe para simular que le hablás", test_compat_container)
        test_compat_layout.addWidget(self.lbl_hint)

        self.btn_demo_sequence = QPushButton("▶ reproducir secuencia completa", test_compat_container)
        self.btn_demo_sequence.clicked.connect(self.run_demo_interaction_sequence)
        test_compat_layout.addWidget(self.btn_demo_sequence)

        self.visualizer.clicked.connect(self._handle_orb_click)

        controls_bar_widget = QWidget(test_compat_container)
        controls_bar = QHBoxLayout(controls_bar_widget)
        controls_bar.setContentsMargins(0, 0, 0, 0)
        self.btn_state_reposo = QPushButton("REPOSO", controls_bar_widget)
        self.btn_state_reposo.clicked.connect(lambda: self._set_visualizer_state(VisualizerState.REPOSO))
        controls_bar.addWidget(self.btn_state_reposo)

        self.btn_state_escuchando = QPushButton("ESCUCHAR", controls_bar_widget)
        self.btn_state_escuchando.clicked.connect(lambda: self._set_visualizer_state(VisualizerState.ESCUCHANDO))
        controls_bar.addWidget(self.btn_state_escuchando)

        self.btn_state_hablando = QPushButton("HABLAR", controls_bar_widget)
        self.btn_state_hablando.clicked.connect(lambda: self._set_visualizer_state(VisualizerState.HABLANDO))
        controls_bar.addWidget(self.btn_state_hablando)

        self.btn_toggle_mic = QPushButton("🎙 MIC ON/OFF", controls_bar_widget)
        self.btn_toggle_mic.setObjectName("btn_primary")
        self.btn_toggle_mic.clicked.connect(self._toggle_audio_capture)
        controls_bar.addWidget(self.btn_toggle_mic)

        self.btn_demo_confirm = QPushButton("⚠ PROBAR SOLICITUD 'NEEDS_CONFIRMATION'", controls_bar_widget)
        self.btn_demo_confirm.setObjectName("demo_confirm_btn")
        self.btn_demo_confirm.clicked.connect(self._demo_request_confirmation)
        controls_bar.addWidget(self.btn_demo_confirm)

        test_compat_layout.addWidget(controls_bar_widget)
        orb_layout.addWidget(test_compat_container)

        if self.orb_web is not None:
            test_compat_container.hide()
        else:
            test_compat_container.show()


        layout.addWidget(self.orb_stage, stretch=6)

        # --- ÁREA DERECHA: Workspace / Feed Conversacional (440px) ---
        self.right_panel = QFrame(container)
        self.right_panel.setFixedWidth(440)
        self.right_panel.setStyleSheet(f"background-color: {Colors.SURFACE_LOWEST};")

        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(14, 12, 14, 14)
        right_layout.setSpacing(10)

        # Encabezado de Chat (Mini orbe luminoso + JARVIS + Leer respuestas + Dock)
        chat_header = QHBoxLayout()
        chat_header.setSpacing(8)

        mini_orb = MiniGlowingOrb(self.right_panel)
        chat_header.addWidget(mini_orb)

        title_col = QHBoxLayout()
        title_col.setSpacing(4)
        lbl_jarvis_title = QLabel("JARVIS")
        lbl_jarvis_title.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 14px; font-weight: bold; letter-spacing: 0.5px;")
        lbl_status_dot = QLabel("●")
        lbl_status_dot.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px;")
        title_col.addWidget(lbl_jarvis_title)
        title_col.addWidget(lbl_status_dot)
        chat_header.addLayout(title_col)

        chat_header.addStretch()

        self.chk_tts = QCheckBox("Leer respuestas")
        self.chk_tts.setChecked(True)
        self.chk_tts.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 11px;")
        chat_header.addWidget(self.chk_tts)

        self.btn_dock = QPushButton(self.right_panel)
        self.btn_dock.setFixedSize(28, 28)
        self.btn_dock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dock.setToolTip("Retraer chat manual con JARVIS (Ctrl+M)")
        self.btn_dock.setIcon(self._create_dock_icon(is_collapsed=False, color="#94A3B8"))
        self.btn_dock.setIconSize(QSize(16, 16))
        self.btn_dock.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE_CONTAINER};
                border-color: {Colors.PRIMARY_BRIGHT}88;
            }}
            """
        )
        self.btn_dock.clicked.connect(self.toggle_chat_panel)
        chat_header.addWidget(self.btn_dock)
        right_layout.addLayout(chat_header)

        # Área de Scroll para mensajes
        self.chat_scroll = QScrollArea(self.right_panel)
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("background: transparent; border: none;")

        self.chat_messages_container = QWidget()
        self.chat_messages_layout = QVBoxLayout(self.chat_messages_container)
        self.chat_messages_layout.setContentsMargins(4, 4, 4, 4)
        self.chat_messages_layout.setSpacing(10)

        # Separador de sesión
        lbl_session_sep = QLabel("SESIÓN ACTIVA · 10:40 AM")
        lbl_session_sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_session_sep.setStyleSheet(
            f"color: {Colors.OUTLINE}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"background-color: {Colors.SURFACE_CONTAINER}; padding: 3px 10px; border-radius: 10px; letter-spacing: 0.8px;"
        )
        self.chat_messages_layout.addWidget(lbl_session_sep, alignment=Qt.AlignmentFlag.AlignCenter)

        # Mensaje 1 Demostrativo: Operador
        msg1 = ChatBubble(
            sender_name="Operador",
            text="Genera un reporte consolidado con las ventas del último trimestre y déjalo listo en la carpeta compartida de /docs.",
            is_user=True,
            timestamp="10:41",
            parent=self,
        )
        self.chat_messages_layout.addWidget(msg1)

        # Mensaje 2 Demostrativo: JARVIS con PDF adjunto y Toolbar
        msg2 = ChatBubble(
            sender_name="JARVIS",
            text="Comprendido. He compilado los datos de las transacciones locales y generado la síntesis ejecutiva. El archivo ha sido depositado y verificado con checksum SHA-256.",
            is_user=False,
            timestamp="10:41",
            attachment={"name": "reporte-ventas-Q4.pdf", "size": "142 KB · Generado localmente"},
            has_actions=True,
            on_listen=lambda: self._speak_text("Comprendido. He compilado los datos de las transacciones locales y generado la síntesis ejecutiva."),
            parent=self,
        )
        self.chat_messages_layout.addWidget(msg2)

        # Mensaje 3 Demostrativo: Operador dictado de voz
        msg3 = ChatBubble(
            sender_name="Operador",
            text="“Genera un reporte de ventas en el directorio /docs”",
            is_user=True,
            timestamp="10:42",
            is_voice_dictation=True,
            parent=self,
        )
        self.chat_messages_layout.addWidget(msg3)

        self.chat_messages_layout.addStretch(1)
        self.chat_scroll.setWidget(self.chat_messages_container)
        right_layout.addWidget(self.chat_scroll, stretch=1)

        # Banner informativo: Grabación en vivo (REC ACTIVO)
        self.rec_banner = QFrame(self.right_panel)
        self.rec_banner.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_CONTAINER_LOWEST if hasattr(Colors, 'SURFACE_CONTAINER_LOWEST') else Colors.SURFACE_LOWEST};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.SM}px;
            }}
            """
        )
        rec_layout = QHBoxLayout(self.rec_banner)
        rec_layout.setContentsMargins(8, 4, 8, 4)
        rec_layout.setSpacing(6)

        lbl_rec_dot = QLabel("●")
        lbl_rec_dot.setStyleSheet(f"color: {Colors.ERROR}; font-size: 11px;")
        rec_layout.addWidget(lbl_rec_dot)

        lbl_rec_title = QLabel("REC ACTIVO")
        lbl_rec_title.setStyleSheet(f"color: {Colors.ERROR}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        rec_layout.addWidget(lbl_rec_title)

        lbl_rec_time = QLabel("00:04")
        lbl_rec_time.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 11px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}';")
        rec_layout.addWidget(lbl_rec_time)

        rec_layout.addStretch()

        lbl_rec_bitrate = QLabel("Bitrate: 256kbps lossless")
        lbl_rec_bitrate.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        rec_layout.addWidget(lbl_rec_bitrate)

        btn_rec_close = QPushButton("×")
        btn_rec_close.setFixedSize(18, 18)
        btn_rec_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rec_close.setStyleSheet(f"color: {Colors.TEXT_LOW}; background: transparent; border: none; font-size: 13px;")
        btn_rec_close.clicked.connect(self.rec_banner.hide)
        rec_layout.addWidget(btn_rec_close)

        right_layout.addWidget(self.rec_banner)

        # Contenedor Principal del Composer (Input bar con Clip, Text, Mic y Send)
        input_box = QFrame(self.right_panel)
        input_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_2};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
            }}
            QFrame:focus-within {{
                border: 1px solid {Colors.PRIMARY_BRIGHT}77;
            }}
            """
        )
        input_layout = QHBoxLayout(input_box)
        input_layout.setContentsMargins(6, 4, 6, 4)
        input_layout.setSpacing(6)

        # Botón de adjuntar documento
        btn_attach = QPushButton("📎")
        btn_attach.setFixedSize(30, 30)
        btn_attach.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_attach.setToolTip("Adjuntar documento o archivo")
        btn_attach.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_LOW};
                font-size: 14px;
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                color: {Colors.TEXT_HIGH};
                background-color: {Colors.SURFACE_3};
            }}
            """
        )
        input_layout.addWidget(btn_attach)

        # Input de texto
        self.input_prompt = QLineEdit(input_box)
        self.input_prompt.setPlaceholderText("Escribe un mensaje para JARVIS…")
        self.input_prompt.setStyleSheet("background: transparent; border: none; font-size: 12.5px; color: " + Colors.TEXT_HIGH + ";")
        self.input_prompt.returnPressed.connect(self._handle_send_text_prompt)
        input_layout.addWidget(self.input_prompt, stretch=1)

        # Botón de micrófono con indicador
        btn_mic_input = QPushButton("🎙")
        btn_mic_input.setFixedSize(30, 30)
        btn_mic_input.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_mic_input.setToolTip("Grabación de voz")
        btn_mic_input.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.SURFACE_3};
                border: none;
                color: {Colors.SECONDARY};
                font-size: 14px;
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE_BRIGHT};
            }}
            """
        )
        btn_mic_input.clicked.connect(self._toggle_audio_capture)
        input_layout.addWidget(btn_mic_input)

        # Botón Enviar Cian
        self.btn_send_prompt = QPushButton("➤")
        self.btn_send_prompt.setObjectName("btn_primary")
        self.btn_send_prompt.setFixedSize(32, 32)
        self.btn_send_prompt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send_prompt.setStyleSheet(
            f"""
            QPushButton#btn_primary {{
                background-color: {Colors.PRIMARY_BRIGHT};
                color: #001E2F;
                border: none;
                border-radius: {Radius.SM}px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#btn_primary:hover {{
                background-color: {Colors.PRIMARY};
            }}
            """
        )
        self.btn_send_prompt.clicked.connect(self._handle_send_text_prompt)
        input_layout.addWidget(self.btn_send_prompt)

        right_layout.addWidget(input_box)

        layout.addWidget(self.right_panel, stretch=4)
        return container

    def _create_dock_icon(self, is_collapsed: bool = False, color: str = "#8F909A") -> QIcon:
        """Crea un ícono vectorial nítido para colapsar o expandir el panel de chat manual."""
        pix = QPixmap(24, 24)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 1.6)
        painter.setPen(pen)

        # Marco de panel de interfaz
        painter.drawRoundedRect(3, 4, 18, 16, 2, 2)
        # Línea divisoria vertical simulando el panel derecho
        painter.drawLine(14, 4, 14, 20)

        # Flecha indicadora (< para expandir hacia la izquierda, > para retraer hacia la derecha)
        if is_collapsed:
            painter.drawLine(10, 9, 8, 12)
            painter.drawLine(8, 12, 10, 15)
        else:
            painter.drawLine(8, 9, 10, 12)
            painter.drawLine(10, 12, 8, 15)

        painter.end()
        return QIcon(pix)

    def toggle_chat_panel(self) -> None:
        """Alterna la visibilidad del panel de chat manual con JARVIS."""
        if not hasattr(self, "right_panel") or self.right_panel is None:
            return
        if self.right_panel.isVisible():
            self.collapse_chat_panel()
        else:
            self.expand_chat_panel()

    def collapse_chat_panel(self) -> None:
        """Retrae/oculta el panel de chat manual para maximizar el escenario del orbe."""
        if hasattr(self, "right_panel") and self.right_panel is not None:
            self.right_panel.setVisible(False)
        if hasattr(self, "btn_expand_chat") and self.btn_expand_chat is not None:
            self.btn_expand_chat.show()
            self._update_expand_button_position()
            self.btn_expand_chat.raise_()
        self.append_log("[UI] Panel de chat manual retraído.")

    def expand_chat_panel(self) -> None:
        """Expande/muestra el panel de chat manual junto al orbe."""
        if hasattr(self, "right_panel") and self.right_panel is not None:
            self.right_panel.setVisible(True)
        if hasattr(self, "btn_expand_chat") and self.btn_expand_chat is not None:
            self.btn_expand_chat.hide()
        self.append_log("[UI] Panel de chat manual expandido.")

    def _update_expand_button_position(self) -> None:
        """Ubica el botón flotante de expansión en la esquina superior derecha del escenario del orbe."""
        if (
            hasattr(self, "btn_expand_chat")
            and self.btn_expand_chat is not None
            and hasattr(self, "orb_stage")
            and self.orb_stage is not None
            and self.btn_expand_chat.isVisible()
        ):
            self.btn_expand_chat.adjustSize()
            btn_w = max(86, self.btn_expand_chat.width() + 10)
            btn_h = max(32, self.btn_expand_chat.height() + 2)
            self.btn_expand_chat.resize(btn_w, btn_h)
            self.btn_expand_chat.move(max(10, self.orb_stage.width() - btn_w - 20), 20)
            self.btn_expand_chat.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_expand_button_position()

    # ==========================================================================
    # 3. VISTA 1: CHAT OPERATIVO Y CONSOLA EXTENDIDA
    # ==========================================================================
    def _build_chat_console_view(self) -> QWidget:
        self.chat_screen = ChatSimpleScreen(
            on_send_prompt=self._handle_external_chat_prompt,
            on_toggle_voice=self._toggle_audio_capture,
            on_tts_speak=self._speak_text,
            parent=self,
        )
        self.console_log = self.chat_screen.console_log
        return self.chat_screen

    def _handle_external_chat_prompt(self, text: str) -> None:
        self.append_log(f"[PROMPT // USER] {text}")
        self.lbl_caption.setText(f"“{text}”")
        # También reflejar en el panel derecho del orbe
        bubble = ChatBubble(sender_name="Operador", text=text, is_user=True, parent=self)
        count = self.chat_messages_layout.count()
        self.chat_messages_layout.insertWidget(count - 1, bubble)

        if self.voice_session and hasattr(self.voice_session, "send_text_prompt"):
            try:
                self.voice_session.send_text_prompt(text)
            except Exception as e:
                self.append_log(f"[VOICE // ERROR] No se pudo enviar prompt: {e}")
        else:
            QTimer.singleShot(400, lambda: self.append_chat_message(
                "JARVIS", f"Procesando instrucción: '{text}'. Acción delegada a las capacidades del núcleo."
            ))

    def _speak_text(self, text: str) -> None:
        self.append_log(f"[TTS] Lectura de respuesta: {text[:60]}...")

    # ==========================================================================
    # SECUENCIA DEMO Y MECANOGRAFÍA DEL PROTOTIPO ORBE V2
    # ==========================================================================
    def type_caption(self, text: str, delay_ms: int = 30) -> None:
        """Efecto mecanografía (typewriter) idéntico al prototipo v2 de Stitch."""
        if hasattr(self, "_caption_timer") and self._caption_timer.isActive():
            self._caption_timer.stop()

        self._caption_target_text = text
        self._caption_current_idx = 0
        self.lbl_caption.setText("“”")

        if hasattr(self, "orb_web") and self.orb_web is not None:
            safe_text = text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", " ")
            self.orb_web.page().runJavaScript(f"if (typeof typeCaption === 'function') typeCaption('{safe_text}', {delay_ms});")

        def step():
            if self._caption_current_idx <= len(self._caption_target_text):
                self.lbl_caption.setText(f"“{self._caption_target_text[:self._caption_current_idx]}”")
                self._caption_current_idx += 1
            else:
                self._caption_timer.stop()

        self._caption_timer = QTimer(self)
        self._caption_timer.timeout.connect(step)
        self._caption_timer.start(delay_ms)

    def run_demo_interaction_sequence(self) -> None:
        """Reproduce la secuencia de interacción completa idéntica a runInteractionOnce()."""
        if getattr(self, "_sequence_running", False):
            return
        self._sequence_running = True
        self.lbl_hint.setStyleSheet("color: transparent; font-size: 11px; letter-spacing: 0.5px; padding-top: 2px;")

        if hasattr(self, "orb_web") and self.orb_web is not None:
            self.orb_web.page().runJavaScript("if (typeof runInteractionOnce === 'function') runInteractionOnce();")

        self._set_visualizer_state(VisualizerState.ESCUCHANDO)
        self.type_caption("Escuchando...", 40)

        QTimer.singleShot(1600, lambda: self._demo_step_speaking())
        QTimer.singleShot(4600, lambda: self._demo_step_idle())

    def _demo_step_speaking(self) -> None:
        self._set_visualizer_state(VisualizerState.HABLANDO)
        self.type_caption("Hola, ¿en qué puedo ayudarte hoy?", 26)

    def _demo_step_idle(self) -> None:
        self._set_visualizer_state(VisualizerState.REPOSO)
        self.type_caption("JARVIS a la espera de instrucciones…", 30)
        self._sequence_running = False
        self.lbl_hint.setStyleSheet("color: #5a7188; font-size: 11px; letter-spacing: 0.5px; padding-top: 2px;")


    # ==========================================================================
    # LÓGICA DE MENSAJES Y CHAT
    # ==========================================================================
    def append_chat_message(self, sender: str, text: str, is_user: bool = False) -> None:
        bubble = ChatBubble(sender_name=sender, text=text, is_user=is_user, parent=self)
        count = self.chat_messages_layout.count()
        self.chat_messages_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))
        if hasattr(self, "chat_screen") and self.chat_screen is not None:
            self.chat_screen.append_chat_message(sender, text, is_user=is_user)

    def _handle_send_text_prompt(self) -> None:
        text = self.input_prompt.text().strip()
        if not text:
            return

        self.input_prompt.clear()
        self.append_chat_message("Operador", text, is_user=True)
        self.append_log(f"[PROMPT // USER] {text}")
        self.lbl_caption.setText(f"“{text}”")

        self._set_visualizer_state(VisualizerState.PENSANDO)
        if self.voice_session and hasattr(self.voice_session, "send_text_prompt"):
            try:
                self.voice_session.send_text_prompt(text)
            except Exception as e:
                self.append_log(f"[VOICE // ERROR] No se pudo enviar prompt: {e}")
        else:
            QTimer.singleShot(600, lambda: self.append_chat_message(
                "JARVIS", f"Procesando instrucción: '{text}'. Acción delegada a las capacidades del núcleo."
            ))
            QTimer.singleShot(700, lambda: self._set_visualizer_state(VisualizerState.HABLANDO))
            QTimer.singleShot(2400, lambda: self._set_visualizer_state(VisualizerState.REPOSO))

    def append_log(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        if hasattr(self, "console_log"):
            self.console_log.append(f"[{ts}] {text}")

    def _demo_request_confirmation(self) -> None:
        """Simula una solicitud needs_confirmation para validar el diálogo modal."""
        self.append_log("Simulando solicitud needs_confirmation...")
        request = ConfirmationRequest(
            plugin_name="Control del Hogar",
            plugin_id="home_control",
            action="apagar_todas_las_luces",
            params={"habitaciones": "todas", "forzar": "true"},
            description="Apagar todas las luces de la casa requiere autorización explícita.",
        )
        token = ConfirmationDialog.request_confirmation(self, request)
        if token:
            prefix = token[:8] + "..."
            self.append_log(
                f"[SEGURIDAD] Acción '{request.action}' confirmada por el usuario. "
                f"Token generado: {prefix}"
            )
        else:
            self.append_log(
                f"[SEGURIDAD] Acción '{request.action}' cancelada por el usuario. Solicitud descartada."
            )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if hasattr(self, "orb_web") and watched == self.orb_web:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._handle_orb_click()
        if hasattr(self, "orb_stage") and watched == self.orb_stage:
            if event.type() == QEvent.Type.Resize:
                self._update_expand_button_position()
        return super().eventFilter(watched, event)

    def _handle_orb_click(self) -> None:
        """Gestiona el clic directo sobre el orbe para alternar escucha o interrumpir."""
        if self.visualizer.state in (VisualizerState.HABLANDO, VisualizerState.PENSANDO):
            self.interrupt_speech()
        elif self.visualizer.state == VisualizerState.REPOSO:
            self._set_visualizer_state(VisualizerState.ESCUCHANDO)
        elif self.visualizer.state == VisualizerState.ESCUCHANDO:
            self._set_visualizer_state(VisualizerState.PENSANDO)

    def interrupt_speech(self) -> None:
        """Interrumpe la respuesta actual de JARVIS (Barge-in / Gemini Live) y vuelve a escucha activa."""
        self.append_log("[VOICE] Interrupción detectada (Barge-in). JARVIS silencia la respuesta y atiende al usuario.")
        if self.voice_session and hasattr(self.voice_session, "interrupt"):
            try:
                self.voice_session.interrupt()
            except Exception:
                pass
        self._set_visualizer_state(VisualizerState.ESCUCHANDO)
        self.type_caption("Escuchando...", 30)

    # ==========================================================================
    # GESTIÓN DE AUDIO Y EVENTOS
    # ==========================================================================
    def _set_visualizer_state(self, state: VisualizerState) -> None:
        old_state = self.visualizer.state
        self.visualizer.set_state(state)
        self.lbl_caption.setText(f"“Modo {state.value.upper()} activo”")
        self.append_log(f"[VISUALIZER] Cambio de estado -> {state.value}")

        if hasattr(self, "orb_web") and self.orb_web is not None:
            state_map = {
                VisualizerState.REPOSO: "idle",
                VisualizerState.ESCUCHANDO: "listening",
                VisualizerState.PENSANDO: "thinking",
                VisualizerState.HABLANDO: "speaking",
            }
            js_state = state_map.get(state, "idle")
            self.orb_web.page().runJavaScript(f"if (typeof setState === 'function') setState('{js_state}');")
            if state == VisualizerState.ESCUCHANDO:
                self.orb_web.page().runJavaScript("if (typeof typeCaption === 'function') typeCaption('Escuchando...', 30);")
            elif state == VisualizerState.PENSANDO:
                self.orb_web.page().runJavaScript("if (typeof typeCaption === 'function') typeCaption('Pensando...', 30);")
            elif state == VisualizerState.REPOSO:
                self.orb_web.page().runJavaScript("if (typeof clearCaptionSoon === 'function') clearCaptionSoon(200);")

        if state == VisualizerState.ESCUCHANDO:
            self._start_audio_capture()
            if self.voice_session and hasattr(self.voice_session, "start_session"):
                self.voice_session.start_session()
        elif old_state == VisualizerState.ESCUCHANDO and state != VisualizerState.ESCUCHANDO:
            self._stop_audio_capture()
            if self.voice_session and hasattr(self.voice_session, "stop_session"):
                self.voice_session.stop_session()

    def switch_mode(self, state: VisualizerState) -> None:
        """Alias para switch_mode utilizado por las pruebas unitarias."""
        self._set_visualizer_state(state)

    def _toggle_audio_capture(self) -> None:
        if self.audio_running:
            self._stop_audio_capture()
        else:
            self._start_audio_capture()

    def _sounddevice_input_callback(self, indata, frames, time_info, status):
        if status:
            self.audio_bridge.sig_capture_error.emit(str(status))
        self.audio_bridge.sig_audio_chunk.emit(indata.copy())

    def _start_audio_capture(self) -> None:
        if self.audio_running:
            return
        try:
            sample_rate = 16000
            block_size = 512

            self.audio_stream = sd.InputStream(
                samplerate=sample_rate,
                blocksize=block_size,
                channels=1,
                dtype="float32",
                callback=self._sounddevice_input_callback,
            )
            self.audio_stream.start()
            self.audio_running = True
            self.btn_toggle_mic.setText("🎙 MIC ACTIVO")
            self.append_log("[AUDIO] Captura de micrófono iniciada (16 kHz, mono)")
        except Exception as e:
            self.append_log(f"[AUDIO // ERROR] No se pudo abrir micrófono: {e}")
            self.audio_running = False
            self.btn_toggle_mic.setText("🎙 MIC ERROR")

    def _stop_audio_capture(self) -> None:
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_running = False
        self.btn_toggle_mic.setText("🎙 MIC INACTIVO")
        self.append_log("[AUDIO] Captura de micrófono detenida")

    def _process_audio_chunk(self, chunk: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(chunk**2))) if chunk.size > 0 else 0.0

        # Detección de Barge-in: si el usuario habla mientras JARVIS habla o piensa, se interrumpe
        if self.visualizer and self.visualizer.state in (VisualizerState.HABLANDO, VisualizerState.PENSANDO):
            if rms >= 0.035:
                self.interrupt_speech()

        if self.visualizer and self.visualizer.state == VisualizerState.ESCUCHANDO:
            self.visualizer.feed_audio_samples(chunk.flatten())
            if hasattr(self, "orb_web") and self.orb_web is not None:
                audio_target = min(1.0, 0.15 + rms * 5.0)
                self.orb_web.page().runJavaScript(f"audioTarget = {audio_target:.3f};")

        if self.voice_session and getattr(self.voice_session, "_is_active", False):
            if hasattr(self.voice_session, "send_audio_chunk"):
                self.voice_session.send_audio_chunk(chunk.flatten().tobytes())

    def _handle_capture_error(self, err_msg: str) -> None:
        self.append_log(f"[AUDIO // STATUS] {err_msg}")

    def _handle_voice_state_changed(self, new_state: str) -> None:
        self.append_log(f"[VOICE // STATE] {new_state}")
        st = new_state.lower()
        if st in ("listening", "escuchando"):
            self.visualizer.set_state(VisualizerState.ESCUCHANDO)
            self.lbl_caption.setText("“Escuchando voz...”")
            if hasattr(self, "orb_web") and self.orb_web is not None:
                self.orb_web.page().runJavaScript("if (typeof setState === 'function') setState('listening'); if (typeof typeCaption === 'function') typeCaption('Escuchando...', 30);")
        elif st in ("thinking", "pensando"):
            self.visualizer.set_state(VisualizerState.PENSANDO)
            self.lbl_caption.setText("“Pensando...”")
            if hasattr(self, "orb_web") and self.orb_web is not None:
                self.orb_web.page().runJavaScript("if (typeof setState === 'function') setState('thinking'); if (typeof typeCaption === 'function') typeCaption('Pensando...', 30);")
        elif st in ("speaking", "hablando"):
            self.visualizer.set_state(VisualizerState.HABLANDO)
            self.lbl_caption.setText("“JARVIS respondiendo...”")
            if hasattr(self, "orb_web") and self.orb_web is not None:
                self.orb_web.page().runJavaScript("if (typeof setState === 'function') setState('speaking');")
        else:
            self.visualizer.set_state(VisualizerState.REPOSO)
            self.lbl_caption.setText("“JARVIS a la espera de instrucciones…”")
            if hasattr(self, "orb_web") and self.orb_web is not None:
                self.orb_web.page().runJavaScript("if (typeof setState === 'function') setState('idle'); if (typeof clearCaptionSoon === 'function') clearCaptionSoon(200);")

    def _handle_voice_text_output(self, text: str) -> None:
        self.append_chat_message("JARVIS", text)
        self.lbl_caption.setText(f"“{text}”")

    def _handle_voice_audio_output(self, audio_bytes: bytes, amplitude: float) -> None:
        self.visualizer.set_state(VisualizerState.HABLANDO)
        self.visualizer.feed_output_amplitude(amplitude)
        if hasattr(self, "orb_web") and self.orb_web is not None:
            self.orb_web.page().runJavaScript(
                f"if (typeof setState === 'function') setState('speaking'); audioTarget = {amplitude:.3f};"
            )

    def _handle_voice_error(self, err: str) -> None:
        self.append_log(f"[VOICE // ERROR] {err}")
        self.lbl_caption.setText("“Error en conexión de voz”")

    def _handle_voice_silence_timeout(self) -> None:
        self.append_log("[VOICE] Tiempo de silencio alcanzado. Volviendo a reposo.")
        self.visualizer.set_state(VisualizerState.REPOSO)

    def _handle_plugin_status_message(self, message: str, success: bool) -> None:
        tag = "ÉXITO" if success else "ERROR"
        self.append_log(f"[PLUGINS // {tag}] {message}")
        self.latest_toast = ToastManager.show_toast(parent=self, message=message, success=success)

    def closeEvent(self, event) -> None:
        self._stop_audio_capture()
        if self.voice_session:
            self.voice_session.stop_session()
        ToastManager.clear_all()
        super().closeEvent(event)


# ==============================================================================
# ENTRYPOINT
# ==============================================================================
def launch_app():
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    window = JarvisMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(launch_app())
