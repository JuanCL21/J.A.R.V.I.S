"""
ui/test_app_settings.py
Prueba de integración offscreen para el botón de Configuración en JarvisMainWindow.
Verifica que btn_settings existe en la ventana principal y que al hacer clic
se abre un SettingsDialog modal.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ui.app import JarvisMainWindow
from ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def main_window(app):
    window = JarvisMainWindow()
    window.fps_timer.stop()
    window.audio_sim_timer.stop()
    yield window
    window.close()


def test_settings_button_exists_and_opens_modal_dialog(main_window):
    """
    Verifica que btn_settings existe en JarvisMainWindow con ícono ⚙ y tooltip 'Configuración',
    y que al hacer clic se abre un SettingsDialog modal activo.
    """
    assert hasattr(main_window, "btn_settings")
    assert main_window.btn_settings.text() == "⚙"
    assert main_window.btn_settings.objectName() == "settings_btn"
    assert main_window.btn_settings.toolTip() == "Configuración"

    dialog_opened_and_verified = False

    def handle_modal():
        nonlocal dialog_opened_and_verified
        active_modal = QApplication.activeModalWidget()
        if isinstance(active_modal, SettingsDialog):
            assert active_modal.isModal()
            assert "CONFIGURACIÓN" in active_modal.windowTitle()
            dialog_opened_and_verified = True
            active_modal.close()

    QTimer.singleShot(30, handle_modal)
    main_window.btn_settings.click()

    assert dialog_opened_and_verified, "El diálogo SettingsDialog debió abrirse de forma modal."
