"""
Diálogo de Confirmación de Acciones Sensibles para JARVIS (spec 4.2).

Cuando el dispatcher del backend retorna needs_confirmation, esta UI presenta un
diálogo modal que muestra explícitamente qué plugin pide la acción, qué acción
específica, y un resumen legible de los parámetros relevantes.

Reglas de seguridad reflejadas acá (no negociables, ver sección 5 de la spec):
- Nunca hay un checkbox de "confiar siempre" de alcance amplio. Si en el futuro se
  agrega una opción de "recordar para esta sesión", debe operar sobre la clave
  granular (plugin_id, capability, session) que use el dispatcher — nunca más amplia.
- El token de confirmación es efímero y se genera ÚNICAMENTE dentro del handler del
  botón "Confirmar", como resultado directo del clic real del usuario. No existe
  ninguna vía para que un componente externo (LLM, script, otro plugin) fabrique o
  inyecte un token válido por su cuenta.
- El diálogo es modal (QDialog.exec bloquea la acción en curso) pero no congela el
  resto de la interfaz: al ser un loop de eventos anidado de Qt, los QTimer del
  visualizador de audio (ui/audio_visualizer.py) siguen disparando y la esfera puede
  seguir animándose en reposo de fondo detrás del diálogo.

Esta pieza no accede a sqlite3 ni a archivos del backend directamente. Recibe los
datos ya resueltos (plugin, acción, parámetros) a través de ConfirmationRequest y
devuelve el token generado (o None si se cancela) — la validación y el consumo real
del token son responsabilidad del dispatcher del backend.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class ConfirmationRequest:
    """
    Datos ya resueltos de una solicitud needs_confirmation del dispatcher.
    Esta UI no interpreta ni valida estos datos, solo los muestra.
    """

    plugin_name: str
    plugin_id: str
    action: str
    params: Dict[str, str] = field(default_factory=dict)
    # Texto opcional en lenguaje natural describiendo la acción, si el dispatcher
    # lo provee. Si no viene, se arma un resumen genérico a partir de action.
    description: Optional[str] = None


class _ParamRow(QFrame):
    """Fila de solo lectura clave: valor dentro del resumen de parámetros."""

    def __init__(self, key: str, value: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)

        key_label = QLabel(f"{key}:")
        key_label.setStyleSheet(
            "color: #6e8fa8; font-family: 'Monospace', 'Consolas', 'Courier New'; "
            "font-size: 12px; font-weight: bold;"
        )
        key_label.setFixedWidth(140)
        key_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        value_label = QLabel(value)
        value_label.setStyleSheet(
            "color: #d8f0ff; font-family: 'Monospace', 'Consolas', 'Courier New'; font-size: 12px;"
        )
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout.addWidget(key_label)
        layout.addWidget(value_label, stretch=1)


class ConfirmationDialog(QDialog):
    """
    Diálogo modal para confirmar acciones sensibles solicitadas por un plugin.

    Uso típico:
        request = ConfirmationRequest(
            plugin_name="Control del Hogar",
            plugin_id="home_control",
            action="apagar_todas_las_luces",
            params={"habitaciones": "todas", "confirmar_apagado_total": "true"},
        )
        token = ConfirmationDialog.request_confirmation(parent_window, request)
        if token is not None:
            dispatcher.confirm_action(request.plugin_id, request.action, token)
    """

    def __init__(self, request: ConfirmationRequest, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._request = request
        self._token: Optional[str] = None

        self.setWindowTitle("JARVIS — Confirmación Requerida")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(560)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #060911;
            }
            QLabel {
                color: #d8f0ff;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )

        self._build_ui()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        card = QFrame(self)
        card.setStyleSheet(
            """
            QFrame#confirm_card {
                background-color: rgba(12, 20, 36, 0.95);
                border: 1px solid rgba(255, 170, 0, 0.45);
                border-radius: 12px;
            }
            """
        )
        card.setObjectName("confirm_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)

        # Encabezado con ícono de alerta y título
        header_layout = QHBoxLayout()
        icon_label = QLabel("⚠")
        icon_label.setStyleSheet("color: #ffaa00; font-size: 22px;")
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel("CONFIRMACIÓN DE ACCIÓN SENSIBLE")
        title_label.setStyleSheet(
            "color: #ffaa00; font-size: 14px; font-weight: bold; letter-spacing: 1px;"
        )
        subtitle_label = QLabel("Un plugin solicita autorización explícita para continuar")
        subtitle_label.setStyleSheet("color: #6e8fa8; font-size: 11px;")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)
        header_layout.addWidget(icon_label)
        header_layout.addSpacing(8)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        card_layout.addLayout(header_layout)

        card_layout.addWidget(self._make_separator())

        # Qué plugin y qué acción
        identity_row = _ParamRow("Plugin", f"{self._request.plugin_name} ({self._request.plugin_id})")
        action_row = _ParamRow("Acción", self._request.action)
        card_layout.addWidget(identity_row)
        card_layout.addWidget(action_row)

        # Descripción legible, si viene del dispatcher
        if self._request.description:
            desc_label = QLabel(self._request.description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(
                "color: #d8f0ff; font-size: 12px; padding: 6px 0px;"
            )
            card_layout.addWidget(desc_label)

        # Resumen de parámetros, si los hay
        if self._request.params:
            card_layout.addWidget(self._make_separator())
            params_title = QLabel("PARÁMETROS")
            params_title.setStyleSheet(
                "color: #6e8fa8; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
            )
            card_layout.addWidget(params_title)

            params_scroll = QScrollArea()
            params_scroll.setWidgetResizable(True)
            params_scroll.setMaximumHeight(160)
            params_scroll.setFrameShape(QFrame.Shape.NoFrame)

            params_container = QWidget()
            params_layout = QVBoxLayout(params_container)
            params_layout.setContentsMargins(0, 4, 0, 4)
            params_layout.setSpacing(4)
            for key, value in self._request.params.items():
                params_layout.addWidget(_ParamRow(str(key), str(value)))
            params_layout.addStretch()

            params_scroll.setWidget(params_container)
            card_layout.addWidget(params_scroll)

        outer.addWidget(card)

        # Botonera: Confirmar / Cancelar. Deliberadamente sin checkbox de
        # "no volver a preguntar" de alcance amplio (ver spec sección 4.2 y 5).
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = QPushButton("CANCELAR")
        self.btn_cancel.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(18, 30, 52, 0.9);
                color: #d8f0ff;
                border: 1px solid rgba(216, 240, 255, 0.25);
                border-radius: 8px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(216, 240, 255, 0.1);
                border: 1px solid #d8f0ff;
            }
            """
        )
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("CONFIRMAR")
        self.btn_confirm.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 170, 0, 0.15);
                color: #ffaa00;
                border: 2px solid #ffaa00;
                border-radius: 8px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 170, 0, 0.30);
                color: #ffffff;
            }
            """
        )
        self.btn_confirm.clicked.connect(self._on_confirm_clicked)
        self.btn_confirm.setDefault(False)
        self.btn_confirm.setAutoDefault(False)
        self.btn_cancel.setDefault(True)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        outer.addLayout(btn_layout)

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(0, 230, 255, 0.15);")
        return sep

    # ------------------------------------------------------------------
    # Generación del token efímero
    # ------------------------------------------------------------------

    def _on_confirm_clicked(self) -> None:
        """
        Genera el token de confirmación ÚNICAMENTE como resultado de este clic real
        del usuario. Nada fuera de este handler puede producir un token válido.
        """
        self._token = secrets.token_urlsafe(24)
        self.accept()

    def confirmation_token(self) -> Optional[str]:
        """Retorna el token generado si el usuario confirmó, o None si canceló/cerró."""
        return self._token

    # ------------------------------------------------------------------
    # API estática de conveniencia
    # ------------------------------------------------------------------

    @staticmethod
    def request_confirmation(
        parent: Optional[QWidget], request: ConfirmationRequest
    ) -> Optional[str]:
        """
        Construye el diálogo, lo ejecuta de forma modal y bloqueante para la acción
        en curso (sin congelar el resto de la interfaz — ver docstring del módulo) y
        retorna el token de confirmación, o None si el usuario canceló o cerró el
        diálogo sin confirmar.
        """
        dialog = ConfirmationDialog(request, parent)
        dialog.exec()
        return dialog.confirmation_token()
