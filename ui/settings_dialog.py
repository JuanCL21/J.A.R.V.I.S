"""
Diálogo de Configuración de JARVIS.
Adaptado fielmente al diseño de Stitch: 'JARVIS - Configuración del Sistema' (ID: ac6643a735ca4097940e1751effc1ea4).

Reglas de seguridad aplicadas:
- La API key nunca se muestra en texto claro después de guardarse, ni siquiera parcialmente.
- La verificación de conexión corre en un QThread separado: nunca bloquea el hilo principal de Qt.
- La clave nunca se loggea ni se emite por ninguna señal de estado/log.
- El guardado usa core.secrets.set_secret() con permisos seguros (0600).
- Tipografía y colores unificados vía ui.theme (IBM Plex Sans / IBM Plex Mono).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Asegurar importación de core desde la raíz del repositorio
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PyQt6.QtCore import QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Colors, Radius, Spacing, Typography

try:
    from core.secrets import get_secret, set_secret
except ImportError:  # pragma: no cover
    get_secret = None
    set_secret = None

try:
    from core.sandbox import get_default_sandbox_base
except ImportError:  # pragma: no cover
    get_default_sandbox_base = None

try:
    from core.plugin_installer import get_allowed_git_hosts
except ImportError:  # pragma: no cover
    get_allowed_git_hosts = None


GEMINI_API_KEY_ENV_NAME = "GEMINI_API_KEY"
GEMINI_GET_KEY_URL = "https://aistudio.google.com/app/apikey"


# ---------------------------------------------------------------------------
# Worker de verificación (corre en hilo aparte, nunca bloquea la UI)
# ---------------------------------------------------------------------------
class GeminiKeyVerificationWorker(QThread):
    """
    Verifica una API key de Gemini realizando una llamada real y liviana
    (listado de modelos accesibles) contra la API, sin tocar el hilo de Qt.
    """

    verification_ok = pyqtSignal(str)
    verification_failed = pyqtSignal(str)

    def __init__(self, api_key: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._api_key = api_key

    def run(self) -> None:
        candidate = (self._api_key or "").strip()
        if not candidate:
            self.verification_failed.emit("La clave está vacía.")
            return

        try:
            from google import genai
        except ImportError:
            self.verification_failed.emit(
                "El paquete 'google-genai' no está instalado en este entorno. "
                "Instálalo con: pip install google-genai"
            )
            return

        try:
            client = genai.Client(api_key=candidate)
            models_seen = 0
            for _ in client.models.list():
                models_seen += 1
                if models_seen >= 1:
                    break
            self.verification_ok.emit(
                "Conexión verificada correctamente. La clave tiene acceso a los modelos de Gemini."
            )
        except Exception as e:
            self.verification_failed.emit(f"No se pudo verificar la clave: {e}")


# ---------------------------------------------------------------------------
# Indicador visual de estado de verificación (Diseño Stitch Card)
# ---------------------------------------------------------------------------
class VerificationStatusIndicator(QFrame):
    """
    Tarjeta de estado de verificación visual con colores y diseño Stitch.
    """

    STATE_IDLE = "idle"
    STATE_CHECKING = "checking"
    STATE_SUCCESS = "success"
    STATE_ERROR = "error"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("verification_indicator")
        self.setStyleSheet(
            f"""
            QFrame#verification_indicator {{
                background-color: {Colors.SURFACE_2};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.LG}px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        self.icon_label = QLabel("○")
        self.icon_label.setFixedSize(30, 30)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        text_container = QVBoxLayout()
        text_container.setContentsMargins(0, 0, 0, 0)
        text_container.setSpacing(3)

        self.title_label = QLabel("ESTADO DE VERIFICACIÓN")
        self.title_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"letter-spacing: 0.5px; color: {Colors.TEXT_MEDIUM};"
        )
        text_container.addWidget(self.title_label)

        self.text_label = QLabel("Sin verificar")
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 12px; line-height: 1.3;")
        text_container.addWidget(self.text_label)

        layout.addLayout(text_container, stretch=1)
        self.set_state(self.STATE_IDLE)

    def set_state(self, state: str, message: Optional[str] = None) -> None:
        palette = {
            self.STATE_IDLE: ("○", Colors.TEXT_LOW, "SIN VERIFICAR", "Sin verificar"),
            self.STATE_CHECKING: ("◌", Colors.WARNING, "VERIFICANDO CONEXIÓN...", "Comprobando credenciales con la API de Gemini..."),
            self.STATE_SUCCESS: ("✓", Colors.SECONDARY, "CONEXIÓN VERIFICADA", "La clave tiene acceso a los modelos de Gemini (gemini-2.0-flash-exp)."),
            self.STATE_ERROR: ("✕", Colors.ERROR, "FALLO DE CONEXIÓN", "No se pudo establecer comunicación con el modelo."),
        }
        icon, color, title, default_msg = palette.get(state, palette[self.STATE_IDLE])
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(
            f"background-color: {color}25; color: {color}; font-size: 16px; font-weight: bold; border-radius: 15px;"
        )
        self.title_label.setText(title)
        self.title_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"letter-spacing: 0.5px; color: {color};"
        )
        self.text_label.setText(message if message else default_msg)
        self.text_label.setStyleSheet(
            f"color: {Colors.TEXT_HIGH if state == self.STATE_SUCCESS else Colors.TEXT_LOW}; font-size: 12px; line-height: 1.3;"
        )


# ---------------------------------------------------------------------------
# Sección: Asistente de Voz (API de Gemini)
# ---------------------------------------------------------------------------
class GeminiApiSection(QWidget):
    """
    Sección principal de configuración del asistente con diseño idéntico a Stitch:
    - Encabezado con tag v2.4-pyqt
    - Card de estado con badge ENCRYPTED_STORE
    - Botón de enlace a Google AI Studio
    - Input de API Key con toggle de visibilidad 👁
    - Botones: GUARDAR CLAVE, VERIFICAR CONEXIÓN, ELIMINAR CLAVE
    - Indicador visual de verificación
    - Resumen de parámetros globales (3 cards)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._verification_worker: Optional[GeminiKeyVerificationWorker] = None
        self._has_saved_key: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 1. Título y Subtítulo
        header_row = QHBoxLayout()
        title = QLabel("ASISTENTE DE VOZ // API DE GEMINI")
        title.setStyleSheet(
            f"color: {Colors.PRIMARY_BRIGHT}; font-size: 13px; font-weight: 700; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        header_row.addWidget(title)

        tag_version = QLabel("v2.4-pyqt")
        tag_version.setStyleSheet(
            f"background-color: {Colors.SURFACE_2}; color: {Colors.TEXT_LOW}; "
            f"font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"padding: 2px 6px; border-radius: {Radius.XS}px; border: 1px solid {Colors.BORDER_STRUCTURAL};"
        )
        header_row.addWidget(tag_version)
        header_row.addStretch()
        layout.addLayout(header_row)

        subtitle = QLabel(
            "JARVIS usa la API de Gemini Live para el reconocimiento y síntesis de voz. "
            "Necesitas una clave de API válida para activar la escucha y respuesta por voz."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 13px; line-height: 1.4;")
        layout.addWidget(subtitle)

        # 2. Card de Estado de Clave Guardada
        self.status_card = QFrame()
        self.status_card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.LG}px;
            }}
            """
        )
        status_card_layout = QHBoxLayout(self.status_card)
        status_card_layout.setContentsMargins(14, 12, 14, 12)
        status_card_layout.setSpacing(12)

        self.status_card_icon = QLabel("✓")
        self.status_card_icon.setFixedSize(30, 30)
        self.status_card_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_card_icon.setStyleSheet(
            f"background-color: {Colors.SECONDARY}22; color: {Colors.SECONDARY}; font-size: 16px; font-weight: bold; border-radius: 15px;"
        )
        status_card_layout.addWidget(self.status_card_icon)

        status_text_col = QVBoxLayout()
        status_text_col.setContentsMargins(0, 0, 0, 0)
        status_text_col.setSpacing(2)

        self.lbl_current_status = QLabel("Clave configurada y activa")
        self.lbl_current_status.setStyleSheet(
            f"color: {Colors.SECONDARY}; font-size: 13px; font-weight: bold;"
        )
        status_text_col.addWidget(self.lbl_current_status)

        self.lbl_status_desc = QLabel("Guardar una nueva credencial reemplazará de forma segura el registro actual.")
        self.lbl_status_desc.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px;")
        status_text_col.addWidget(self.lbl_status_desc)

        status_card_layout.addLayout(status_text_col, stretch=1)

        badge_encrypted = QLabel("ENCRYPTED_STORE")
        badge_encrypted.setStyleSheet(
            f"background-color: {Colors.SURFACE_2}; color: {Colors.SECONDARY}; "
            f"font-size: 10px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"padding: 4px 8px; border-radius: {Radius.SM}px; border: 1px solid {Colors.SECONDARY}44;"
        )
        status_card_layout.addWidget(badge_encrypted)

        layout.addWidget(self.status_card)

        # 3. Botón Enlace a Google AI Studio
        link_row = QHBoxLayout()
        self.btn_get_key = QPushButton("↗ Obtener API Key en Google AI Studio")
        self.btn_get_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_get_key.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.SURFACE_1};
                color: {Colors.PRIMARY_BRIGHT};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE_2};
                border: 1px solid {Colors.PRIMARY};
                color: #FFFFFF;
            }}
            """
        )
        self.btn_get_key.clicked.connect(self._open_get_key_page)
        link_row.addWidget(self.btn_get_key)
        link_row.addStretch()
        layout.addLayout(link_row)

        # 4. Campo de Ingreso de Clave con Toggle de Visibilidad
        input_container = QVBoxLayout()
        input_container.setSpacing(6)

        label_row = QHBoxLayout()
        field_label = QLabel("Pegar nueva API Key:")
        field_label.setStyleSheet(
            f"color: {Colors.TEXT_HIGH}; font-size: 12px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;"
        )
        label_row.addWidget(field_label)

        hint_format = QLabel("AIzaSy...")
        hint_format.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 11px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        label_row.addWidget(hint_format)
        label_row.addStretch()
        input_container.addLayout(label_row)

        input_field_box = QFrame()
        input_field_box.setFixedHeight(42)
        input_field_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
            }}
            """
        )
        box_layout = QHBoxLayout(input_field_box)
        box_layout.setContentsMargins(10, 0, 10, 0)
        box_layout.setSpacing(6)

        self.input_api_key = QLineEdit()
        self.input_api_key.setPlaceholderText("Ingresa tu Gemini API Key...")
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_api_key.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_HIGH};
                font-size: 13px;
                font-family: '{Typography.FONT_FAMILY_MONO}';
            }}
            """
        )
        self.input_api_key.textEdited.connect(self._on_key_input_edited)
        box_layout.addWidget(self.input_api_key, stretch=1)

        self.btn_toggle_visibility = QPushButton("👁")
        self.btn_toggle_visibility.setFixedSize(30, 30)
        self.btn_toggle_visibility.setCheckable(True)
        self.btn_toggle_visibility.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_visibility.setToolTip("Alternar visibilidad")
        self.btn_toggle_visibility.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_LOW};
                border: none;
                font-size: 14px;
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                color: {Colors.PRIMARY_BRIGHT};
                background-color: {Colors.SURFACE_3};
            }}
            QPushButton:checked {{
                color: {Colors.PRIMARY};
            }}
            """
        )
        self.btn_toggle_visibility.toggled.connect(self._on_toggle_visibility)
        box_layout.addWidget(self.btn_toggle_visibility)

        input_container.addWidget(input_field_box)

        # Hint de Privacidad
        privacy_hint = QLabel("🔒 La clave se guarda localmente y nunca se registra en los logs ni en la consola de eventos.")
        privacy_hint.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px;")
        input_container.addWidget(privacy_hint)

        layout.addLayout(input_container)

        # 5. Botones de Acción (Guardar, Verificar, Eliminar)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.btn_save = QPushButton("Guardar Clave")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.PRIMARY};
                color: #FFFFFF;
                border: 1px solid {Colors.PRIMARY};
                border-radius: {Radius.MD}px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background-color: {Colors.PRIMARY_HOVER};
                border-color: {Colors.PRIMARY_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {Colors.SURFACE_2};
                color: {Colors.TEXT_LOW};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        self.btn_save.clicked.connect(self._on_save_clicked)
        action_row.addWidget(self.btn_save)

        self.btn_verify = QPushButton("Verificar Conexión")
        self.btn_verify.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_verify.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.SURFACE_1};
                color: {Colors.SECONDARY};
                border: 1px solid {Colors.SECONDARY}66;
                border-radius: {Radius.MD}px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SECONDARY}22;
                border-color: {Colors.SECONDARY};
                color: #FFFFFF;
            }}
            QPushButton:disabled {{
                background-color: {Colors.SURFACE_2};
                color: {Colors.TEXT_LOW};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        self.btn_verify.clicked.connect(self._on_verify_clicked)
        action_row.addWidget(self.btn_verify)

        action_row.addStretch()

        self.btn_delete = QPushButton("Eliminar Clave")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.SURFACE_1};
                color: {Colors.ERROR};
                border: 1px solid {Colors.ERROR}55;
                border-radius: {Radius.MD}px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ERROR_CONTAINER};
                border-color: {Colors.ERROR};
                color: #FFFFFF;
            }}
            QPushButton:disabled {{
                background-color: {Colors.SURFACE_2};
                color: {Colors.TEXT_LOW};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        action_row.addWidget(self.btn_delete)

        layout.addLayout(action_row)

        # 6. Indicador de Estado de Verificación
        self.status_indicator = VerificationStatusIndicator()
        layout.addWidget(self.status_indicator)

        # 7. Resumen de Parámetros Globales (Solo Lectura) - 3 Cards Grid
        summary_title = QLabel("RESUMEN DE PARÁMETROS GLOBALES (SOLO LECTURA)")
        summary_title.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        layout.addWidget(summary_title)

        grid_params = QGridLayout()
        grid_params.setSpacing(10)

        # Card 1: Raíz Sandbox
        sandbox_path = "No disponible"
        if get_default_sandbox_base is not None:
            try:
                sandbox_path = str(get_default_sandbox_base())
            except Exception:
                sandbox_path = "No disponible"
        grid_params.addWidget(self._param_card("Raíz Sandbox", "📁", sandbox_path, Colors.PRIMARY), 0, 0)

        # Card 2: Git Fail-Closed
        hosts_text = "github.com, gitlab.com"
        if get_allowed_git_hosts is not None:
            try:
                hosts_text = ", ".join(sorted(get_allowed_git_hosts()))
            except Exception:
                hosts_text = "No disponible"
        grid_params.addWidget(self._param_card("Git Fail-Closed", "🛡", hosts_text, Colors.SECONDARY), 0, 1)

        # Card 3: Hardware Audio
        grid_params.addWidget(self._param_card("Hardware Audio", "🔊", "Fase 5 - Gemini Live", Colors.TEXT_LOW), 0, 2)

        layout.addLayout(grid_params)
        layout.addStretch()

        self.refresh_saved_key_status()

    @staticmethod
    def _param_card(label: str, icon: str, value: str, accent_color: str) -> QFrame:
        card = QFrame()
        card.setFixedHeight(64)
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
            }}
            """
        )
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 8, 12, 8)
        c_layout.setSpacing(4)

        top_row = QHBoxLayout()
        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 10px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        top_row.addWidget(lbl)
        top_row.addStretch()
        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 12px;")
        top_row.addWidget(ic)
        c_layout.addLayout(top_row)

        val = QLabel(value)
        val.setToolTip(value)
        val.setStyleSheet(
            f"color: {accent_color}; font-size: 11px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        c_layout.addWidget(val)
        return card

    # -- Helpers de estado -------------------------------------------------
    def refresh_saved_key_status(self) -> None:
        """Consulta si ya existe una clave guardada, sin exponerla nunca."""
        self._has_saved_key = False
        if get_secret is not None:
            try:
                existing = get_secret(GEMINI_API_KEY_ENV_NAME)
                self._has_saved_key = bool(existing and existing.strip())
            except Exception:
                self._has_saved_key = False

        if self._has_saved_key:
            self.lbl_current_status.setText("Clave configurada y activa")
            self.lbl_current_status.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 13px; font-weight: bold;")
            self.lbl_status_desc.setText("Guardar una nueva credencial reemplazará de forma segura el registro actual.")
            self.status_card_icon.setText("✓")
            self.status_card_icon.setStyleSheet(
                f"background-color: {Colors.SECONDARY}22; color: {Colors.SECONDARY}; font-size: 16px; font-weight: bold; border-radius: 15px;"
            )
        else:
            self.lbl_current_status.setText("No hay ninguna clave configurada todavía")
            self.lbl_current_status.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 13px; font-weight: bold;")
            self.lbl_status_desc.setText("Ingresa tu Gemini API Key a continuación para activar la voz interactiva.")
            self.status_card_icon.setText("○")
            self.status_card_icon.setStyleSheet(
                f"background-color: {Colors.TEXT_LOW}22; color: {Colors.TEXT_LOW}; font-size: 16px; font-weight: bold; border-radius: 15px;"
            )

        self.btn_delete.setEnabled(self._has_saved_key)
        self.status_indicator.set_state(VerificationStatusIndicator.STATE_IDLE)

    # -- Slots de UI ---------------------------------------------------------
    def _open_get_key_page(self) -> None:
        QDesktopServices.openUrl(QUrl(GEMINI_GET_KEY_URL))

    def _on_toggle_visibility(self, checked: bool) -> None:
        self.input_api_key.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _on_key_input_edited(self, _text: str) -> None:
        self.status_indicator.set_state(VerificationStatusIndicator.STATE_IDLE)

    def _on_save_clicked(self) -> None:
        candidate = self.input_api_key.text().strip()
        if not candidate:
            self.status_indicator.set_state(
                VerificationStatusIndicator.STATE_ERROR,
                "El campo está vacío. Pega una clave antes de guardar.",
            )
            return
        if set_secret is None:
            self.status_indicator.set_state(
                VerificationStatusIndicator.STATE_ERROR,
                "No se pudo acceder al módulo de almacenamiento seguro (core.secrets).",
            )
            return
        try:
            set_secret(GEMINI_API_KEY_ENV_NAME, candidate)
        except Exception as e:
            self.status_indicator.set_state(
                VerificationStatusIndicator.STATE_ERROR,
                f"No se pudo guardar la clave: {e}",
            )
            return

        self.input_api_key.clear()
        self.btn_toggle_visibility.setChecked(False)
        self.refresh_saved_key_status()
        self.status_indicator.set_state(
            VerificationStatusIndicator.STATE_SUCCESS,
            "Clave guardada correctamente. Podés verificar la conexión ahora.",
        )

    def _on_verify_clicked(self) -> None:
        typed = self.input_api_key.text().strip()
        key_to_verify: Optional[str] = None

        if typed:
            key_to_verify = typed
        elif self._has_saved_key and get_secret is not None:
            try:
                key_to_verify = get_secret(GEMINI_API_KEY_ENV_NAME)
            except Exception:
                key_to_verify = None

        if not key_to_verify:
            self.status_indicator.set_state(
                VerificationStatusIndicator.STATE_ERROR,
                "No hay ninguna clave para verificar (ni escrita ni guardada).",
            )
            return

        self.btn_verify.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.status_indicator.set_state(VerificationStatusIndicator.STATE_CHECKING)

        self._verification_worker = GeminiKeyVerificationWorker(key_to_verify, parent=self)
        self._verification_worker.verification_ok.connect(self._on_verification_ok)
        self._verification_worker.verification_failed.connect(self._on_verification_failed)
        self._verification_worker.finished.connect(self._on_verification_finished)
        self._verification_worker.start()

    def _on_verification_ok(self, message: str) -> None:
        self.status_indicator.set_state(VerificationStatusIndicator.STATE_SUCCESS, message)

    def _on_verification_failed(self, message: str) -> None:
        self.status_indicator.set_state(VerificationStatusIndicator.STATE_ERROR, message)

    def _on_verification_finished(self) -> None:
        self.btn_verify.setEnabled(True)
        self.btn_save.setEnabled(True)

    def _on_delete_clicked(self) -> None:
        if set_secret is None:
            self.status_indicator.set_state(
                VerificationStatusIndicator.STATE_ERROR,
                "No se pudo acceder al módulo de almacenamiento seguro (core.secrets).",
            )
            return
        try:
            set_secret(GEMINI_API_KEY_ENV_NAME, "")
        except Exception as e:
            self.status_indicator.set_state(
                VerificationStatusIndicator.STATE_ERROR,
                f"No se pudo eliminar la clave: {e}",
            )
            return

        self.input_api_key.clear()
        self.refresh_saved_key_status()
        self.status_indicator.set_state(
            VerificationStatusIndicator.STATE_IDLE, "Clave eliminada."
        )


# ---------------------------------------------------------------------------
# Sección: General
# ---------------------------------------------------------------------------
class GeneralSection(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("CONFIGURACIÓN GENERAL")
        title.setStyleSheet(
            f"color: {Colors.PRIMARY_BRIGHT}; font-size: 13px; font-weight: 700; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        layout.addWidget(title)

        info = QLabel(
            "Información general de esta instancia de JARVIS. Estos valores son de "
            "solo lectura y definen el enclave local seguro."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 13px;")
        layout.addWidget(info)

        sandbox_path = "No disponible"
        if get_default_sandbox_base is not None:
            try:
                sandbox_path = str(get_default_sandbox_base())
            except Exception:
                sandbox_path = "No disponible"

        box = QFrame()
        box.setStyleSheet(
            f"background-color: {Colors.SURFACE_1}; border: 1px solid {Colors.BORDER_STRUCTURAL}; "
            f"border-radius: {Radius.MD}px; padding: 14px;"
        )
        b_layout = QVBoxLayout(box)
        b_layout.setSpacing(8)

        lbl = QLabel("Ruta local de ejecución segura (Sandbox Base):")
        lbl.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 12px; font-weight: bold;")
        b_layout.addWidget(lbl)

        val = QLabel(sandbox_path)
        val.setStyleSheet(
            f"color: {Colors.PRIMARY}; font-size: 12px; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"background-color: {Colors.SURFACE_LOWEST}; padding: 8px 12px; border-radius: {Radius.SM}px;"
        )
        b_layout.addWidget(val)

        layout.addWidget(box)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Sección: Seguridad
# ---------------------------------------------------------------------------
class SecuritySection(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("POLÍTICAS DE SEGURIDAD Y AISLAMIENTO")
        title.setStyleSheet(
            f"color: {Colors.PRIMARY_BRIGHT}; font-size: 13px; font-weight: 700; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        layout.addWidget(title)

        info = QLabel(
            "Estos valores reflejan la política de seguridad activa del núcleo. "
            "No son editables desde esta pantalla para evitar debilitar el "
            "confinamiento de plugins por error."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 13px;")
        layout.addWidget(info)

        hosts_text = "github.com, gitlab.com"
        if get_allowed_git_hosts is not None:
            try:
                hosts_text = ", ".join(sorted(get_allowed_git_hosts()))
            except Exception:
                hosts_text = "No disponible"

        box = QFrame()
        box.setStyleSheet(
            f"background-color: {Colors.SURFACE_1}; border: 1px solid {Colors.BORDER_STRUCTURAL}; "
            f"border-radius: {Radius.MD}px; padding: 14px;"
        )
        b_layout = QVBoxLayout(box)
        b_layout.setSpacing(8)

        lbl = QLabel("Dominios Git Autorizados (fail-closed):")
        lbl.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 12px; font-weight: bold;")
        b_layout.addWidget(lbl)

        val = QLabel(hosts_text)
        val.setStyleSheet(
            f"color: {Colors.SECONDARY}; font-size: 12px; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"background-color: {Colors.SURFACE_LOWEST}; padding: 8px 12px; border-radius: {Radius.SM}px;"
        )
        b_layout.addWidget(val)

        layout.addWidget(box)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Sección: Audio (placeholder, dependiente de Fase 5)
# ---------------------------------------------------------------------------
class AudioSection(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("DISPOSITIVOS DE ENTRADA / SALIDA")
        title.setStyleSheet(
            f"color: {Colors.PRIMARY_BRIGHT}; font-size: 13px; font-weight: 700; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        layout.addWidget(title)

        box = QFrame()
        box.setStyleSheet(
            f"background-color: {Colors.SURFACE_1}; border: 1px solid {Colors.BORDER_STRUCTURAL}; "
            f"border-radius: {Radius.MD}px; padding: 14px;"
        )
        b_layout = QVBoxLayout(box)
        b_layout.setSpacing(8)

        placeholder = QLabel(
            "Selector de dispositivo disponible en Fase 5 - Audio + Gemini Live.\n"
            "Actualmente el sistema utiliza los dispositivos predeterminados del hardware de audio del sistema operativo."
        )
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 12px; line-height: 1.5;")
        b_layout.addWidget(placeholder)

        layout.addWidget(box)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Diálogo principal de Configuración (Fiel al diseño Stitch)
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    """
    Diálogo modal de configuración con estructura de Stitch:
    - Barra superior con badge de Enclave y botón de cierre.
    - Barra lateral de navegación (240px) con lista de secciones y card inferior de motor.
    - Stack con secciones temáticas.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        Typography.initialize_fonts()

        self.setWindowTitle("JARVIS — CONFIGURACIÓN")
        self.setModal(True)
        self.resize(840, 600)
        self.setMinimumSize(720, 500)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {Colors.SURFACE_LOWEST};
            }}
            """
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 1. Top Bar (h-12 / 48px)
        top_bar = QFrame(self)
        top_bar.setFixedHeight(48)
        top_bar.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border-bottom: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 16, 0)
        top_layout.setSpacing(12)

        # Icon + Title
        lbl_icon = QLabel("⚙")
        lbl_icon.setStyleSheet(f"color: {Colors.PRIMARY_BRIGHT}; font-size: 16px;")
        top_layout.addWidget(lbl_icon)

        lbl_title = QLabel("JARVIS — CONFIGURACIÓN")
        lbl_title.setStyleSheet(
            f"color: {Colors.TEXT_HIGH}; font-size: 13px; font-weight: bold; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        top_layout.addWidget(lbl_title)

        # Enclave status chip
        enclave_chip = QLabel("● LOCAL ENCLAVE · ZERO EXFILTRATION")
        enclave_chip.setStyleSheet(
            f"background-color: {Colors.SURFACE_2}; color: {Colors.SECONDARY}; "
            f"font-size: 10px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"padding: 3px 8px; border-radius: {Radius.SM}px; border: 1px solid {Colors.SECONDARY}44;"
        )
        top_layout.addWidget(enclave_chip)
        top_layout.addStretch()

        # Botón de cerrar superior
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("Cerrar ventana")
        self.btn_close.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MEDIUM};
                border: none;
                border-radius: {Radius.SM}px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.ERROR}33;
                color: {Colors.ERROR};
            }}
            """
        )
        self.btn_close.clicked.connect(self.close)
        top_layout.addWidget(self.btn_close)

        outer_layout.addWidget(top_bar)

        # 2. Cuerpo: Sidebar de Secciones + Stack
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar lateral izquierda (240px)
        sidebar_frame = QFrame(self)
        sidebar_frame.setFixedWidth(240)
        sidebar_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border-right: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(8, 16, 8, 16)
        sidebar_layout.setSpacing(10)

        # Label 'Secciones'
        lbl_sections = QLabel("SECCIONES")
        lbl_sections.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1.5px; font-family: '{Typography.FONT_FAMILY_MONO}'; padding-left: 8px;"
        )
        sidebar_layout.addWidget(lbl_sections)

        # Lista de Navegación
        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet(
            f"""
            QListWidget {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_MEDIUM};
                font-size: 13px;
                font-weight: 500;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 14px;
                margin-bottom: 3px;
                border-radius: {Radius.MD}px;
                border-left: 3px solid transparent;
            }}
            QListWidget::item:hover {{
                background-color: {Colors.SURFACE_2};
                color: {Colors.TEXT_HIGH};
            }}
            QListWidget::item:selected {{
                background-color: {Colors.SURFACE_2};
                color: {Colors.PRIMARY_BRIGHT};
                border-left: 3px solid {Colors.PRIMARY};
                font-weight: bold;
            }}
            """
        )

        self.stack = QStackedWidget()

        sections = [
            ("General", GeneralSection()),
            ("Asistente de Voz (Gemini)", GeminiApiSection()),
            ("Seguridad", SecuritySection()),
            ("Audio", AudioSection()),
        ]

        for label_text, widget in sections:
            self.nav_list.addItem(QListWidgetItem(label_text))
            self.stack.addWidget(widget)

        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav_list.setCurrentRow(1)  # Abrir por defecto en Gemini

        sidebar_layout.addWidget(self.nav_list, stretch=1)

        # Card inferior de motor
        motor_card = QFrame()
        motor_card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_2};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
                padding: 10px;
            }}
            """
        )
        m_layout = QVBoxLayout(motor_card)
        m_layout.setContentsMargins(8, 8, 8, 8)
        m_layout.setSpacing(6)

        m_top = QHBoxLayout()
        lbl_motor = QLabel("MOTOR DIALOG")
        lbl_motor.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 9px; font-weight: bold; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        m_top.addWidget(lbl_motor)
        m_top.addStretch()

        m_dot = QLabel("●")
        m_dot.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px;")
        m_top.addWidget(m_dot)
        m_layout.addLayout(m_top)

        lbl_engine = QLabel("PyQt6 / QSettings")
        lbl_engine.setStyleSheet(
            f"color: {Colors.TEXT_MEDIUM}; font-size: 11px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        m_layout.addWidget(lbl_engine)

        # Mini barra de estado
        p_bar = QFrame()
        p_bar.setFixedHeight(3)
        p_bar.setStyleSheet(f"background-color: {Colors.SECONDARY}; border-radius: 1px;")
        m_layout.addWidget(p_bar)

        sidebar_layout.addWidget(motor_card)

        body_layout.addWidget(sidebar_frame)
        body_layout.addWidget(self.stack, stretch=1)

        outer_layout.addLayout(body_layout, stretch=1)

    @classmethod
    def open_settings(cls, parent: Optional[QWidget] = None) -> "SettingsDialog":
        dialog = cls(parent=parent)
        dialog.exec()
        return dialog


def _standalone_preview() -> None:  # pragma: no cover
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = SettingsDialog()
    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    _standalone_preview()
