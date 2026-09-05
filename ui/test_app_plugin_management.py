"""
Test offscreen de integración de PluginManagementDialog y PluginCatalogScreen en JarvisMainWindow.
Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_app_plugin_management.py -v

Verifica:
1. El botón de escudo para gestión de plugins existe en la ventana principal.
2. Al hacer clic, se abre un diálogo modal que contiene un PluginCatalogScreen embebido.
3. refresh() se invoca sobre PluginCatalogScreen al abrir el diálogo.
4. El callback on_status_message propaga los mensajes hacia la consola de eventos log_console.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.app import JarvisMainWindow
from ui.plugin_catalog import PluginCatalogScreen, CuratedPluginInfo
from ui.plugin_management_dialog import PluginManagementDialog


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


def test_shield_button_exists_in_main_window(main_window):
    """Verifica que el botón con ícono de escudo existe en la ventana principal con su configuración."""
    assert hasattr(main_window, "btn_plugins")
    assert main_window.btn_plugins.text() == "🛡"
    assert main_window.btn_plugins.objectName() == "plugins_shield_btn"
    assert main_window.btn_plugins.toolTip() == "Gestión de Plugins"


def test_click_shield_opens_dialog_containing_catalog_screen(main_window, monkeypatch):
    """
    Verifica que al hacer clic en el botón de escudo se abra un diálogo modal
    que contiene una instancia de PluginCatalogScreen.
    """
    dialog_verified = False

    def handle_active_dialog():
        nonlocal dialog_verified
        active_modal = QApplication.activeModalWidget()
        if isinstance(active_modal, PluginManagementDialog):
            assert hasattr(active_modal, "catalog_screen")
            assert isinstance(active_modal.catalog_screen, PluginCatalogScreen)
            assert "GESTIÓN DE PLUGINS" in active_modal.windowTitle()
            dialog_verified = True
            active_modal.close()

    QTimer.singleShot(30, handle_active_dialog)
    main_window.btn_plugins.click()

    assert dialog_verified, "El diálogo PluginManagementDialog debió abrirse de forma modal"


def test_refresh_called_when_dialog_opened(main_window, monkeypatch):
    """
    Verifica que refresh() sea invocado sobre PluginCatalogScreen al abrir el diálogo,
    asegurando que las tarjetas muestren el estado de instalación más actualizado.
    """
    refresh_call_count = 0
    original_refresh = PluginCatalogScreen.refresh

    def spy_refresh(self):
        nonlocal refresh_call_count
        refresh_call_count += 1
        return original_refresh(self)

    monkeypatch.setattr(PluginCatalogScreen, "refresh", spy_refresh)

    def handle_and_close():
        active_modal = QApplication.activeModalWidget()
        if isinstance(active_modal, PluginManagementDialog):
            active_modal.close()

    QTimer.singleShot(30, handle_and_close)
    main_window.btn_plugins.click()

    # refresh() se llama en __init__ de PluginCatalogScreen y explícitamente en open_management
    assert refresh_call_count >= 1, "refresh() debe ser invocado al abrir el diálogo de gestión"


def test_status_message_appears_in_log_console(main_window):
    """
    Verifica que el callback on_status_message conectado al diálogo
    refleje el mensaje en self.log_console de la ventana principal.
    """
    # 1. Éxito
    main_window._handle_plugin_status_message("El plugin 'Monitor del Sistema' se instaló correctamente.", True)
    log_text = main_window.log_console.toPlainText()
    assert "[PLUGINS // ÉXITO]" in log_text
    assert "El plugin 'Monitor del Sistema' se instaló correctamente." in log_text

    # 2. Error
    main_window._handle_plugin_status_message("No se pudo instalar el plugin, intentá de nuevo.", False)
    log_text_after = main_window.log_console.toPlainText()
    assert "[PLUGINS // ERROR]" in log_text_after
    assert "No se pudo instalar el plugin, intentá de nuevo." in log_text_after


def test_end_to_end_on_status_message_from_dialog_callback(main_window, monkeypatch):
    """
    Verifica de punta a punta que cuando el diálogo se abre con on_status_message configurado,
    la invocación del callback desde dentro de PluginCatalogScreen llega hasta log_console.
    """
    def handle_and_trigger_status():
        active_modal = QApplication.activeModalWidget()
        if isinstance(active_modal, PluginManagementDialog):
            # Simular emisión de callback desde el catálogo interno
            active_modal.catalog_screen._on_status_message("Instalación completada de prueba", True)
            active_modal.close()

    QTimer.singleShot(30, handle_and_trigger_status)
    main_window.btn_plugins.click()

    log_text = main_window.log_console.toPlainText()
    assert "Instalación completada de prueba" in log_text
    assert "[PLUGINS // ÉXITO]" in log_text
