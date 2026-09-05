"""
Test offscreen de integración de ConfirmationDialog en JarvisMainWindow (ui/app.py).
Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_app_confirmation.py -v

Verifica:
- El botón de demo de confirmación existe en la interfaz y está conectado.
- Al hacer clic en el botón de demo, se dispara la solicitud needs_confirmation.
- Si el usuario confirma en el diálogo, se registra el prefijo del token (primeros 8 caracteres)
  y NUNCA el token completo en texto plano.
- Si el usuario cancela, queda registrado el descarte en la consola de eventos.
- El flujo completo se ejecuta de forma offscreen sin excepciones.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.app import JarvisMainWindow
from ui.confirmation_dialog import ConfirmationDialog, ConfirmationRequest


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def main_window(app):
    window = JarvisMainWindow()
    # Detener temporizadores de simulación de audio/telemetría durante los asserts para evitar ruido
    window.fps_timer.stop()
    window.audio_sim_timer.stop()
    yield window
    window.close()


def test_demo_confirmation_button_exists_and_styled(main_window):
    """Verifica la existencia y configuración básica del botón de demo."""
    assert hasattr(main_window, "btn_demo_confirm")
    assert main_window.btn_demo_confirm.text() == "⚠ PROBAR SOLICITUD 'NEEDS_CONFIRMATION'"
    assert main_window.btn_demo_confirm.objectName() == "demo_confirm_btn"


def test_demo_confirmation_confirmed_flow_logs_prefix_only(main_window, monkeypatch):
    """
    Verifica que al confirmar la acción:
    1. Se registre la recepción de needs_confirmation.
    2. Se muestre solo el prefijo del token (8 caracteres + '...').
    3. NUNCA se exponga el token completo en la consola de eventos.
    """
    secret_token = "efimero_token_super_secreto_para_dispatcher_12345"

    def mock_request_confirmation(parent, request: ConfirmationRequest):
        assert request.plugin_id == "home_control"
        assert request.action == "apagar_todas_las_luces"
        assert "habitaciones" in request.params
        return secret_token

    monkeypatch.setattr(ConfirmationDialog, "request_confirmation", mock_request_confirmation)

    main_window.btn_demo_confirm.click()

    log_content = main_window.log_console.toPlainText()
    expected_prefix = secret_token[:8] + "..."

    # Verificar que el log contiene el prefijo esperado
    assert expected_prefix in log_content
    # REGLA CRÍTICA: El token completo NUNCA debe estar expuesto en el texto del log
    assert secret_token not in log_content
    assert "Acción 'apagar_todas_las_luces' confirmada por el usuario" in log_content


def test_demo_confirmation_cancelled_flow_logs_rejection(main_window, monkeypatch):
    """Verifica que al cancelar la acción, la consola registre el descarte."""
    def mock_request_confirmation_cancel(parent, request: ConfirmationRequest):
        return None

    monkeypatch.setattr(ConfirmationDialog, "request_confirmation", mock_request_confirmation_cancel)

    main_window.btn_demo_confirm.click()

    log_content = main_window.log_console.toPlainText()
    assert "Acción 'apagar_todas_las_luces' cancelada por el usuario. Solicitud descartada." in log_content


def test_demo_confirmation_end_to_end_offscreen_dialog_confirm(main_window):
    """
    Prueba offscreen end-to-end con el diálogo real de Qt:
    Utiliza un QTimer para simular el clic de confirmación real del usuario
    sobre el diálogo modal cuando se abre.
    """
    dialog_handled = False

    def handle_active_dialog():
        nonlocal dialog_handled
        active_modal = QApplication.activeModalWidget()
        if isinstance(active_modal, ConfirmationDialog):
            dialog_handled = True
            # Simular el clic en el botón Confirmar del diálogo real
            active_modal.btn_confirm.click()

    # Programar la respuesta del usuario para cuando el diálogo modal esté en exec()
    QTimer.singleShot(30, handle_active_dialog)

    main_window.btn_demo_confirm.click()

    assert dialog_handled, "El diálogo ConfirmationDialog debió haber sido activado y manipulado"
    log_content = main_window.log_console.toPlainText()
    assert "Acción 'apagar_todas_las_luces' confirmada por el usuario" in log_content
    assert "Token generado:" in log_content


def test_demo_confirmation_end_to_end_offscreen_dialog_cancel(main_window):
    """
    Prueba offscreen end-to-end con el diálogo real de Qt:
    Simula que el usuario presiona Cancelar.
    """
    dialog_handled = False

    def handle_active_dialog_cancel():
        nonlocal dialog_handled
        active_modal = QApplication.activeModalWidget()
        if isinstance(active_modal, ConfirmationDialog):
            dialog_handled = True
            active_modal.btn_cancel.click()

    QTimer.singleShot(30, handle_active_dialog_cancel)

    main_window.btn_demo_confirm.click()

    assert dialog_handled
    log_content = main_window.log_console.toPlainText()
    assert "Acción 'apagar_todas_las_luces' cancelada por el usuario. Solicitud descartada." in log_content
