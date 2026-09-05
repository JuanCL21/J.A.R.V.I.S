"""
Pruebas offscreen para ToastNotification y ToastManager (spec 4.6).
Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_toast_notification.py -v

Verifica:
1. El toast se instancia y se muestra al invocar _handle_plugin_status_message en JarvisMainWindow.
2. El toast se auto-cierra después del tiempo configurado.
3. Los estilos, acentos y colores difieren correctamente entre mensajes de éxito (#00e6ff) y error (#ff5c5c).
4. Múltiples toasts se apilan verticalmente sin solaparse.
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from ui.app import JarvisMainWindow
from ui.toast_notification import ToastManager, ToastNotification


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def main_window(app):
    window = JarvisMainWindow()
    window.fps_timer.stop()
    window.audio_sim_timer.stop()
    window.show()
    yield window
    ToastManager.clear_all()
    window.close()


def test_toast_instantiated_and_shown_on_handle_plugin_status_message(main_window):
    """
    Requisito 1: El toast se instancia y se muestra al invocar _handle_plugin_status_message.
    """
    msg = "Plugin 'open_interpreter' instalado correctamente."
    main_window._handle_plugin_status_message(msg, success=True)

    # Verificar que se instanció y almacenó en la ventana
    assert hasattr(main_window, "latest_toast")
    toast = main_window.latest_toast
    assert toast is not None
    assert isinstance(toast, ToastNotification)
    assert toast.message == msg
    assert toast.success is True
    assert toast.isVisible()

    # Verificar que también se registró en log_console (no en reemplazo de)
    log_text = main_window.log_console.toPlainText()
    assert "[PLUGINS // ÉXITO]" in log_text
    assert msg in log_text


def test_toast_auto_closes_after_configured_time(main_window):
    """
    Requisito 2: El toast se auto-cierra después del tiempo configurado.
    """
    toast = ToastNotification(
        parent=main_window,
        message="Auto close test",
        success=True,
        duration_ms=3500,
    )
    toast.show()

    assert toast.isVisible()
    assert toast.auto_close_timer.isActive()
    assert toast.auto_close_timer.interval() == 3500

    # Disparar el timeout del timer
    toast.auto_close_timer.timeout.emit()

    # Tras el timeout, el toast debe haberse cerrado
    assert toast.isHidden() or not toast.isVisible()


def test_toast_styling_differs_between_success_and_error(main_window):
    """
    Requisito 3: Colores y estilo difieren correctamente entre éxito y error.
    - Éxito: acento cian #00e6ff, tag 'ÉXITO'.
    - Error: acento rojo #ff5c5c, tag 'ERROR'.
    """
    toast_success = ToastNotification(
        parent=main_window,
        message="Operación exitosa",
        success=True,
    )
    toast_error = ToastNotification(
        parent=main_window,
        message="Operación fallida",
        success=False,
    )

    # Verificación de etiquetas
    assert "ÉXITO" in toast_success.tag_label.text()
    assert "ERROR" in toast_error.tag_label.text()

    # Verificación de paleta cian (#00e6ff) vs roja (#ff5c5c)
    assert "#00e6ff" in toast_success.tag_label.styleSheet()
    assert "#00e6ff" in toast_success.container.styleSheet()

    assert "#ff5c5c" in toast_error.tag_label.styleSheet()
    assert "#ff5c5c" in toast_error.container.styleSheet()

    toast_success.close()
    toast_error.close()


def test_toast_stacking_without_overlap(main_window):
    """
    Requisito 4: Múltiples toasts se apilan verticalmente sin solaparse.
    """
    ToastManager.clear_all()

    toast1 = ToastManager.show_toast(parent=main_window, message="Mensaje 1", success=True)
    toast2 = ToastManager.show_toast(parent=main_window, message="Mensaje 2", success=False)

    # Ambos deben estar activos
    assert len(ToastManager._active_toasts) == 2

    # Sus posiciones en Y deben ser diferentes (apilamiento vertical sin solapamiento)
    assert toast1.y() != toast2.y()
    # La distancia vertical entre ellos debe ser al menos la altura de un toast
    assert abs(toast1.y() - toast2.y()) >= (toast1.height() or 30)

    ToastManager.clear_all()
    assert len(ToastManager._active_toasts) == 0
