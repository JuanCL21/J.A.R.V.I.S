"""
ui/test_app_dock_chat.py
Pruebas de integración offscreen para el botón de retraer / expandir el chat manual con JARVIS.
Verifica que:
1. btn_dock existe en la esquina superior derecha del panel de chat.
2. Hacer clic en btn_dock retrae (oculta) el panel derecho (right_panel) y activa el botón flotante de expansión (btn_expand_chat).
3. Hacer clic en btn_expand_chat expande (muestra) el panel de chat nuevamente y oculta el botón flotante.
4. El atajo Ctrl+M (shortcut_toggle_chat) alterna el estado entre retraído y expandido.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ui.app import JarvisMainWindow


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
    window.close()


def test_btn_dock_exists_and_has_tooltip(main_window):
    """Verifica que btn_dock existe con tooltip informativo y tamaño correcto."""
    assert hasattr(main_window, "btn_dock")
    assert main_window.btn_dock is not None
    assert "Retraer chat manual" in main_window.btn_dock.toolTip()
    assert main_window.btn_dock.width() == 28
    assert main_window.btn_dock.height() == 28


def test_collapse_and_expand_chat_panel(main_window):
    """Verifica que al hacer clic en btn_dock se retrae el panel y al hacer clic en btn_expand_chat se expande."""
    assert hasattr(main_window, "right_panel")
    assert hasattr(main_window, "btn_expand_chat")

    # Inicialmente el panel derecho está visible y el botón de expandir está oculto
    assert main_window.right_panel.isVisible()
    assert not main_window.btn_expand_chat.isVisible()

    # Clic en btn_dock para retraer
    main_window.btn_dock.click()
    assert not main_window.right_panel.isVisible(), "right_panel debe quedar oculto tras retraer"
    assert main_window.btn_expand_chat.isVisible(), "btn_expand_chat debe mostrarse al retraer"

    # Clic en btn_expand_chat para restaurar
    main_window.btn_expand_chat.click()
    assert main_window.right_panel.isVisible(), "right_panel debe volver a ser visible tras expandir"
    assert not main_window.btn_expand_chat.isVisible(), "btn_expand_chat debe ocultarse tras expandir"


def test_shortcut_toggle_chat(main_window):
    """Verifica que el atajo Ctrl+M alterna el panel de chat."""
    assert hasattr(main_window, "shortcut_toggle_chat")
    assert main_window.shortcut_toggle_chat is not None

    # Estado inicial visible
    assert main_window.right_panel.isVisible()

    # Disparar atajo
    main_window.shortcut_toggle_chat.activated.emit()
    assert not main_window.right_panel.isVisible()

    # Disparar atajo nuevamente
    main_window.shortcut_toggle_chat.activated.emit()
    assert main_window.right_panel.isVisible()
