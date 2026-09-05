"""
Pruebas offscreen para Modo Avanzado en PluginManagementDialog (spec 4.4).
Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_plugin_management_advanced.py -v

Verifica los requisitos críticos de auditoría:
1. El toggle/pestaña de Modo Avanzado existe y está oculto/cerrado por defecto.
2. El botón 'Instalar' está deshabilitado hasta que se haya resuelto un commit (no se puede instalar sin pasar por 'Resolver' primero).
3. El botón 'Promover a curado' no aparece si el plugin ya está curado.
4. Promover sin llenar reviewed_by no invoca promote_to_curated (validación de formulario antes de tocar la base de datos).
5. Una URL con esquema no permitido (ej. ext::...) ingresada en el campo se rechaza en la UI con un mensaje claro, sin llegar a invocar resolve_git_ref.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from core.plugin_installer import PluginInstaller
from core.plugin_registry import PluginRegistry
from ui.plugin_management_dialog import PluginManagementDialog, PromoteCuratedDialog


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def mock_registry(tmp_path: Path):
    """Crea una base de datos temporal aislada para pruebas de registro de plugins."""
    db_path = tmp_path / "test_mgmt_advanced.db"
    return PluginRegistry(db_path=str(db_path))


@pytest.fixture
def dialog(app, mock_registry):
    installer = PluginInstaller(registry=mock_registry)
    dlg = PluginManagementDialog(registry=mock_registry, installer=installer)
    dlg.show()
    yield dlg
    dlg.close()


def test_advanced_mode_toggle_exists_and_hidden_by_default(dialog):
    """
    Requisito 1: El toggle/pestaña de Modo Avanzado existe y está oculto/cerrado por defecto.
    """
    assert hasattr(dialog, "btn_toggle_advanced")
    assert hasattr(dialog, "advanced_panel")

    # El botón debe existir y no estar chequeado
    assert not dialog.btn_toggle_advanced.isChecked()

    # El panel de Modo Avanzado debe estar oculto por defecto
    assert dialog.advanced_panel.isHidden() or not dialog.advanced_panel.isVisible()
    # El catálogo curado debe estar visible
    assert not dialog.catalog_screen.isHidden()

    # Al activar el toggle, se muestra el panel avanzado y se oculta el catálogo
    dialog.btn_toggle_advanced.setChecked(True)
    assert not dialog.advanced_panel.isHidden()
    assert dialog.advanced_panel.isVisible()
    assert dialog.catalog_screen.isHidden()

    # Al desactivarlo, vuelve al estado inicial
    dialog.btn_toggle_advanced.setChecked(False)
    assert dialog.advanced_panel.isHidden()
    assert not dialog.catalog_screen.isHidden()


def test_install_button_disabled_until_commit_resolved(dialog, monkeypatch):
    """
    Requisito 2: El botón 'Instalar' está deshabilitado hasta que se haya resuelto
    un commit (no se puede instalar sin pasar por 'Resolver' primero).
    """
    dialog.btn_toggle_advanced.setChecked(True)

    # Inicialmente deshabilitado
    assert hasattr(dialog, "btn_install_advanced")
    assert not dialog.btn_install_advanced.isEnabled()

    # Simular ingreso de URL válida
    dialog.input_source_url.setText("https://github.com/example/sample-plugin.git")
    dialog.input_ref.setText("HEAD")

    # Intentar instalar antes de resolver no debe tener efecto
    dialog._on_install_clicked()
    assert not dialog.btn_install_advanced.isEnabled()
    assert "Debe resolver el commit" in dialog.lbl_advanced_error.text()

    # Mockear resolve_git_ref para retornar un hash SHA-1 válido de 40 caracteres
    fake_sha = "a" * 40
    monkeypatch.setattr(
        "ui.plugin_management_dialog.resolve_git_ref",
        lambda source_url, ref: fake_sha,
    )

    # Clic en resolver
    dialog._on_resolve_clicked()

    # Tras resolución exitosa, el botón debe habilitarse y el SHA debe mostrarse
    assert dialog.btn_install_advanced.isEnabled()
    assert dialog.lbl_resolved_commit.text() == fake_sha


def test_promote_button_visibility_rules_curated_vs_unverified(dialog, mock_registry):
    """
    Requisito 3: El botón 'Promover a curado' no aparece si el plugin ya está curado,
    y solo aparece si el plugin está en estado 'no_verificado'.
    """
    dialog.btn_toggle_advanced.setChecked(True)

    assert hasattr(dialog, "btn_promote")
    # Inicialmente oculto cuando no hay plugin seleccionado
    assert dialog.btn_promote.isHidden()

    # Registrar un plugin no_verificado
    mock_registry.register_plugin(
        plugin_id="plugin_unverified",
        active_commit_hash="1" * 40,
        source_url="https://github.com/example/unverified.git",
    )

    # Actualizar la vista con el plugin no_verificado
    dialog.input_plugin_id.setText("plugin_unverified")
    dialog._update_plugin_status_display("plugin_unverified")
    assert not dialog.btn_promote.isHidden()
    assert dialog.btn_promote.isVisible()
    assert "NO VERIFICADO" in dialog.lbl_plugin_status.text()

    # Ahora promover el plugin a curado en la base de datos
    mock_registry.promote_to_curated(
        plugin_id="plugin_unverified",
        reviewed_by="auditor_lead@jarvis.local",
    )

    # Actualizar la vista: el botón 'Promover a curado' NO debe aparecer
    dialog._update_plugin_status_display("plugin_unverified")
    assert dialog.btn_promote.isHidden()
    assert not dialog.btn_promote.isVisible()
    assert "CURADO" in dialog.lbl_plugin_status.text()


def test_promote_without_reviewed_by_fails_validation_without_touching_db(dialog, mock_registry, monkeypatch):
    """
    Requisito 4: Promover sin llenar reviewed_by no invoca promote_to_curated
    (validación de formulario antes de tocar la base de datos).
    """
    mock_registry.register_plugin(
        plugin_id="plugin_for_promote",
        active_commit_hash="2" * 40,
        source_url="https://github.com/example/promo.git",
    )

    # 1. Probar la validación del diálogo modal secundario PromoteCuratedDialog
    sub_dialog = PromoteCuratedDialog(parent=dialog, plugin_id="plugin_for_promote")
    sub_dialog.show()
    sub_dialog.input_reviewed_by.setText("")  # Vacío
    sub_dialog._validate_and_accept()

    # No debe haberse aceptado el diálogo y el error debe estar visible
    assert sub_dialog.result() != QDialog.DialogCode.Accepted
    assert not sub_dialog.lbl_error.isHidden()
    assert "obligatorio" in sub_dialog.lbl_error.text().lower()

    # Con solo espacios en blanco tampoco debe aceptar
    sub_dialog.input_reviewed_by.setText("   ")
    sub_dialog._validate_and_accept()
    assert sub_dialog.result() != QDialog.DialogCode.Accepted

    # 2. Espiar promote_to_curated para confirmar que NUNCA es invocado si el diálogo es cancelado
    mock_promote = MagicMock(wraps=mock_registry.promote_to_curated)
    monkeypatch.setattr(dialog.registry, "promote_to_curated", mock_promote)

    # Simular que el diálogo se cancela (rechaza)
    monkeypatch.setattr(
        PromoteCuratedDialog,
        "exec",
        lambda self: QDialog.DialogCode.Rejected,
    )

    dialog.input_plugin_id.setText("plugin_for_promote")
    dialog._on_promote_clicked()

    mock_promote.assert_not_called()

    # Verificar que el plugin sigue estando no_verificado en la base de datos
    plugin = mock_registry.get_plugin("plugin_for_promote")
    assert plugin["status"] == "no_verificado"


def test_adversarial_url_scheme_rejected_in_ui_without_calling_resolve_git_ref(dialog, monkeypatch):
    """
    Requisito 5: Una URL con esquema no permitido (ej. ext::...) ingresada en el campo
    se rechaza en la UI con un mensaje claro, sin llegar a invocar resolve_git_ref.
    """
    dialog.btn_toggle_advanced.setChecked(True)

    mock_resolve = MagicMock()
    monkeypatch.setattr("ui.plugin_management_dialog.resolve_git_ref", mock_resolve)

    malicious_urls = [
        'ext::sh -c "touch /tmp/pwned"',
        "ssh://git@github.com/repo.git",
        "file:///etc/passwd",
        "https://evil-untrusted-host.com/repo.git",
        "-u/some/flag",
    ]

    for bad_url in malicious_urls:
        dialog.input_source_url.setText(bad_url)
        dialog._on_resolve_clicked()

        # resolve_git_ref NO debe ser invocado
        mock_resolve.assert_not_called()

        # El mensaje de error debe estar visible y explicar el rechazo
        assert not dialog.lbl_advanced_error.isHidden()
        assert dialog.lbl_advanced_error.isVisible()
        assert "no permitida" in dialog.lbl_advanced_error.text().lower()

        # El botón de instalación debe continuar deshabilitado
        assert not dialog.btn_install_advanced.isEnabled()
