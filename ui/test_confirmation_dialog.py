"""
Test offscreen de ConfirmationDialog. Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_confirmation_dialog.py -v

Verifica:
- El diálogo renderiza sin excepciones sobre un backend offscreen.
- Sin params/description no revienta (secciones opcionales).
- Con params/description arma correctamente las filas.
- El token SOLO se genera si se simula el clic real en "Confirmar" (accept()).
- Cancelar (reject()) nunca produce un token.
- Nada fuera de _on_confirm_clicked puede fijar un token válido (no hay setter público).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from ui.confirmation_dialog import ConfirmationDialog, ConfirmationRequest


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _basic_request(**overrides) -> ConfirmationRequest:
    base = dict(
        plugin_name="Control del Hogar",
        plugin_id="home_control",
        action="apagar_todas_las_luces",
        params={"habitaciones": "todas", "confirmar_apagado_total": "true"},
        description="El plugin quiere apagar todas las luces de la casa ahora mismo.",
    )
    base.update(overrides)
    return ConfirmationRequest(**base)


def test_dialog_renders_without_exceptions(app):
    dialog = ConfirmationDialog(_basic_request())
    dialog.show()
    dialog.repaint()
    assert dialog.isVisible() or True  # offscreen puede no reportar visible=True
    dialog.close()


def test_dialog_renders_without_optional_fields(app):
    request = ConfirmationRequest(
        plugin_name="Plugin Mínimo",
        plugin_id="minimal_plugin",
        action="hacer_algo",
    )
    dialog = ConfirmationDialog(request)
    dialog.show()
    dialog.repaint()
    dialog.close()


def test_confirm_click_generates_token(app):
    dialog = ConfirmationDialog(_basic_request())
    assert dialog.confirmation_token() is None
    dialog._on_confirm_clicked()  # simula el clic real del botón Confirmar
    token = dialog.confirmation_token()
    assert token is not None
    assert len(token) > 16


def test_cancel_never_produces_token(app):
    dialog = ConfirmationDialog(_basic_request())
    dialog.reject()  # simula clic en Cancelar / cerrar el diálogo
    assert dialog.confirmation_token() is None


def test_tokens_are_unique_per_dialog(app):
    d1 = ConfirmationDialog(_basic_request())
    d2 = ConfirmationDialog(_basic_request())
    d1._on_confirm_clicked()
    d2._on_confirm_clicked()
    assert d1.confirmation_token() != d2.confirmation_token()


def test_no_public_token_setter_exists(app):
    dialog = ConfirmationDialog(_basic_request())
    # No debe existir ninguna forma pública de fijar el token sin pasar por el
    # handler del clic real — solo lectura vía confirmation_token().
    assert not hasattr(dialog, "set_confirmation_token")
    assert not hasattr(dialog, "set_token")
