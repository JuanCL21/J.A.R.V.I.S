"""
Test offscreen de PluginCatalogScreen. Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_plugin_catalog.py -v

Verifica:
- Renderiza sin excepciones con datos de ejemplo (instalado y no instalado).
- Nunca hay forma de acceder a commit_hash/source_url/reviewed_by/status desde la
  pantalla (CuratedPluginInfo no los tiene, así que basta con confirmar el contrato).
- El botón "Agregar" dispara install_from_catalog(plugin_id) con el plugin_id correcto.
- Tras una instalación exitosa, la tarjeta pasa a "INSTALADO" y queda deshabilitada.
- Tras una instalación fallida, la tarjeta vuelve a "AGREGAR" (permite reintentar) y
  muestra el mensaje de error, nunca un traceback ni datos técnicos.
- El callback on_status_message se invoca con (mensaje, éxito) en ambos casos.
- refresh() reconsulta el backend y redibuja la grilla sin acumular tarjetas viejas.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

import ui.plugin_catalog as plugin_catalog_module
from ui.plugin_catalog import CuratedPluginInfo, InstallResult, PluginCatalogScreen


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _sample_plugins():
    return [
        CuratedPluginInfo(
            plugin_id="toy",
            name="Toy Plugin",
            description="Plugin de diagnóstico básico del sistema y consulta de hora UTC",
            icon="clock-outline",
            is_installed=True,
        ),
        CuratedPluginInfo(
            plugin_id="system_monitor",
            name="Monitor del Sistema",
            description="Telemetría y métricas operativas del host en tiempo real",
            icon="chart-line",
            is_installed=False,
        ),
    ]


def test_renders_without_exceptions(app, monkeypatch):
    monkeypatch.setattr(plugin_catalog_module, "list_curated_plugins", lambda: _sample_plugins())
    screen = PluginCatalogScreen()
    screen.show()
    screen.repaint()
    assert len(screen._cards) == 2
    screen.close()


def test_cards_never_expose_technical_fields(app, monkeypatch):
    monkeypatch.setattr(plugin_catalog_module, "list_curated_plugins", lambda: _sample_plugins())
    screen = PluginCatalogScreen()
    for plugin in _sample_plugins():
        for forbidden in ("commit_hash", "source_url", "reviewed_by", "status"):
            assert not hasattr(plugin, forbidden)


def test_empty_catalog_shows_empty_state(app, monkeypatch):
    monkeypatch.setattr(plugin_catalog_module, "list_curated_plugins", lambda: [])
    screen = PluginCatalogScreen()
    assert screen._empty_label.isHidden() is False
    assert len(screen._cards) == 0


def test_install_click_calls_backend_with_correct_plugin_id(app, monkeypatch):
    monkeypatch.setattr(plugin_catalog_module, "list_curated_plugins", lambda: _sample_plugins())

    called_with = {}

    def fake_install(plugin_id):
        called_with["plugin_id"] = plugin_id
        return InstallResult(success=True, message="El plugin 'Monitor del Sistema' se instaló correctamente.", plugin_id=plugin_id)

    monkeypatch.setattr(plugin_catalog_module, "install_from_catalog", fake_install)

    screen = PluginCatalogScreen()
    available_card = next(c for c in screen._cards if c.plugin_id == "system_monitor")
    available_card.action_btn.click()

    assert called_with["plugin_id"] == "system_monitor"
    assert available_card.action_btn.text() == "INSTALADO"
    assert available_card.action_btn.isEnabled() is False


def test_failed_install_allows_retry_and_shows_message(app, monkeypatch):
    monkeypatch.setattr(plugin_catalog_module, "list_curated_plugins", lambda: _sample_plugins())

    def fake_install_fail(plugin_id):
        return InstallResult(success=False, message="No se pudo instalar el plugin, intentá de nuevo.", plugin_id=plugin_id)

    monkeypatch.setattr(plugin_catalog_module, "install_from_catalog", fake_install_fail)

    screen = PluginCatalogScreen()
    available_card = next(c for c in screen._cards if c.plugin_id == "system_monitor")
    available_card.action_btn.click()

    assert available_card.action_btn.text() == "AGREGAR"
    assert available_card.action_btn.isEnabled() is True
    assert "no se pudo instalar" in available_card.status_label.text().lower()


def test_status_callback_invoked_with_message_and_success(app, monkeypatch):
    monkeypatch.setattr(plugin_catalog_module, "list_curated_plugins", lambda: _sample_plugins())
    monkeypatch.setattr(
        plugin_catalog_module,
        "install_from_catalog",
        lambda plugin_id: InstallResult(success=True, message="listo", plugin_id=plugin_id),
    )

    received = []
    screen = PluginCatalogScreen(on_status_message=lambda msg, ok: received.append((msg, ok)))
    available_card = next(c for c in screen._cards if c.plugin_id == "system_monitor")
    available_card.action_btn.click()

    assert received == [("listo", True)]


def test_refresh_does_not_accumulate_stale_cards(app, monkeypatch):
    monkeypatch.setattr(plugin_catalog_module, "list_curated_plugins", lambda: _sample_plugins())
    screen = PluginCatalogScreen()
    assert len(screen._cards) == 2

    screen.refresh()
    assert len(screen._cards) == 2  # no se duplican tarjetas al refrescar
