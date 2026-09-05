"""
Notificaciones Toast no bloqueantes para JARVIS (spec 4.6).

Muestra alertas flotantes en la esquina inferior derecha de la ventana principal
cuando llegan eventos de estado (on_status_message).

Características:
- Ventana sin marco (FramelessWindowHint | Tool) que no roba el foco.
- Paleta visual del proyecto (#00e6ff para éxito, #ff5c5c para error).
- Auto-cierre con QTimer después de un intervalo configurable (3500ms por defecto).
- Apilamiento vertical dinámico para evitar solapamiento entre múltiples toasts.
- Manejo robusto del ciclo de vida del objeto Qt evitando referencias huérfanas.
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ToastNotification(QWidget):
    """
    Widget de notificación flotante no bloqueante con auto-cierre.
    """

    DEFAULT_DURATION_MS = 3500

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        message: str = "",
        success: bool = True,
        duration_ms: int = DEFAULT_DURATION_MS,
    ):
        super().__init__(parent)
        self.message = message
        self.success = success
        self.duration_ms = duration_ms

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setFixedWidth(340)

        # Configuración de paleta visual
        accent_color = "#00e6ff" if success else "#ff5c5c"
        bg_color = "rgba(6, 15, 25, 0.94)" if success else "rgba(28, 8, 8, 0.94)"
        tag_text = "✓ ÉXITO" if success else "✕ ERROR"

        # Frame contenedor con borde y esquinas redondeadas
        self.container = QFrame(self)
        self.container.setObjectName("toast_container")
        self.container.setStyleSheet(
            f"""
            QFrame#toast_container {{
                background-color: {bg_color};
                border: 1px solid {accent_color};
                border-radius: 8px;
            }}
            """
        )

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(12, 10, 10, 10)
        container_layout.setSpacing(10)

        # Columna de contenido
        content_box = QVBoxLayout()
        content_box.setSpacing(2)

        self.tag_label = QLabel(tag_text)
        self.tag_label.setStyleSheet(
            f"color: {accent_color}; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
        )
        content_box.addWidget(self.tag_label)

        self.msg_label = QLabel(message)
        self.msg_label.setWordWrap(True)
        self.msg_label.setStyleSheet("color: #d8f0ff; font-size: 11px;")
        content_box.addWidget(self.msg_label)

        container_layout.addLayout(content_box, stretch=1)

        # Botón de cierre manual
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: #6e8fa8;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {accent_color};
            }}
            """
        )
        self.btn_close.clicked.connect(self.close)
        container_layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignTop)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.container)

        self.adjustSize()

        # Timer para auto-cierre
        self.auto_close_timer = QTimer(self)
        self.auto_close_timer.setSingleShot(True)
        self.auto_close_timer.timeout.connect(self.close)
        if duration_ms > 0:
            self.auto_close_timer.start(duration_ms)

        # Salvaguardas de ciclo de vida
        if parent is not None:
            try:
                parent.destroyed.connect(lambda *_: self._on_parent_destroyed())
            except (AttributeError, RuntimeError):
                pass
        self.destroyed.connect(lambda *_: ToastManager.remove_toast(self))

    def _on_parent_destroyed(self) -> None:
        try:
            if self.auto_close_timer.isActive():
                self.auto_close_timer.stop()
            self.close()
        except RuntimeError:
            pass

    def closeEvent(self, event) -> None:
        """Notifica al ToastManager cuando se cierra para reacomodar la pila."""
        try:
            if self.auto_close_timer.isActive():
                self.auto_close_timer.stop()
        except RuntimeError:
            pass
        ToastManager.remove_toast(self)
        super().closeEvent(event)


class ToastManager:
    """
    Gestor de pila vertical para notificaciones toast.
    Evita el solapamiento posicionando las alertas una sobre otra
    en la esquina inferior derecha de la ventana contenedora.
    """

    _active_toasts: List[ToastNotification] = []

    @classmethod
    def _prune_inactive(cls) -> None:
        """Limpia toasts destruidos para evitar fugas de memoria o errores C++."""
        valid: List[ToastNotification] = []
        for t in cls._active_toasts:
            try:
                # Solo descartamos si el objeto C++ subyacente fue eliminado
                _ = t.objectName()
                valid.append(t)
            except RuntimeError:
                pass
        cls._active_toasts = valid

    @classmethod
    def show_toast(
        cls,
        parent: Optional[QWidget],
        message: str,
        success: bool = True,
        duration_ms: int = ToastNotification.DEFAULT_DURATION_MS,
    ) -> ToastNotification:
        """
        Crea, posiciona y muestra una nueva notificación toast apilada.
        """
        cls._prune_inactive()
        toast = ToastNotification(
            parent=parent,
            message=message,
            success=success,
            duration_ms=duration_ms,
        )
        cls._active_toasts.append(toast)
        toast.show()
        cls.reposition_toasts(parent)
        return toast

    @classmethod
    def reposition_toasts(cls, parent: Optional[QWidget] = None) -> None:
        """
        Calcula las coordenadas (x, y) de cada toast para que se apilen
        verticalmente de abajo hacia arriba sin solaparse.
        """
        cls._prune_inactive()
        margin_x = 24
        margin_y = 24
        spacing = 8

        base_x = 800 - margin_x
        base_y = 600 - margin_y

        if parent is not None:
            try:
                if parent.isVisible():
                    parent_pos = parent.mapToGlobal(QPoint(0, 0))
                    base_x = parent_pos.x() + parent.width() - margin_x
                    base_y = parent_pos.y() + parent.height() - margin_y
            except RuntimeError:
                pass

        current_y = base_y
        for toast in reversed(cls._active_toasts):
            try:
                toast_w = toast.width() or 340
                toast_h = toast.height() or 56
                current_y -= toast_h
                toast.move(base_x - toast_w, current_y)
                current_y -= spacing
            except RuntimeError:
                pass

    @classmethod
    def remove_toast(cls, toast: ToastNotification) -> None:
        """Elimina un toast cerrado de la lista y reacomoda los restantes."""
        try:
            if toast in cls._active_toasts:
                cls._active_toasts.remove(toast)
        except (RuntimeError, ValueError):
            pass
        cls._prune_inactive()

    @classmethod
    def clear_all(cls) -> None:
        """Cierra y vacía todos los toasts activos."""
        toasts = list(cls._active_toasts)
        for t in toasts:
            try:
                if t.auto_close_timer.isActive():
                    t.auto_close_timer.stop()
                t.close()
            except RuntimeError:
                pass
        cls._active_toasts.clear()
