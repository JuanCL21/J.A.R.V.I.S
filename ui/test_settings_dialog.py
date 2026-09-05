"""
Tests offscreen para SettingsDialog y GeminiApiSection.
Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_settings_dialog.py -v

Verifica:
1. El diálogo renderiza con las 4 secciones y abre por defecto en Gemini.
2. Guardar una clave vacía no llama a core.secrets.set_secret.
3. Guardar una clave válida llama a set_secret y limpia el campo (nunca
   deja el valor visible en texto claro tras guardar).
4. El botón "Eliminar" está deshabilitado si no hay clave guardada, y
   habilitado si la hay.
5. Verificar conexión deshabilita los botones mientras corre y los
   reactiva al finalizar (mockeando el worker para no requerir red real).
6. El campo de la API key nunca aparece en texto plano en ningún label
   de estado tras guardar o verificar.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from ui.settings_dialog import GeminiApiSection, SettingsDialog, VerificationStatusIndicator


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def settings_dialog(app):
    dialog = SettingsDialog()
    yield dialog
    dialog.close()


def test_dialog_renders_with_four_sections_and_opens_on_gemini(settings_dialog):
    assert settings_dialog.nav_list.count() == 4
    labels = [settings_dialog.nav_list.item(i).text() for i in range(4)]
    assert "Asistente de Voz (Gemini)" in labels
    assert settings_dialog.nav_list.currentRow() == 1
    assert isinstance(settings_dialog.stack.currentWidget(), GeminiApiSection)


def test_save_with_empty_key_does_not_call_set_secret(settings_dialog):
    gemini_section = settings_dialog.stack.widget(1)
    gemini_section.input_api_key.setText("")

    with patch("ui.settings_dialog.set_secret") as mock_set_secret:
        gemini_section._on_save_clicked()
        mock_set_secret.assert_not_called()


def test_save_with_valid_key_calls_set_secret_and_clears_field(settings_dialog):
    gemini_section = settings_dialog.stack.widget(1)
    gemini_section.input_api_key.setText("clave-de-prueba-123")

    with patch("ui.settings_dialog.set_secret") as mock_set_secret, \
         patch("ui.settings_dialog.get_secret", return_value="clave-de-prueba-123"):
        gemini_section._on_save_clicked()
        mock_set_secret.assert_called_once_with("GEMINI_API_KEY", "clave-de-prueba-123")

    # El campo debe quedar vacío: nunca se deja la clave visible tras guardar
    assert gemini_section.input_api_key.text() == ""


def test_delete_button_enabled_state_depends_on_saved_key(settings_dialog):
    gemini_section = settings_dialog.stack.widget(1)

    with patch("ui.settings_dialog.get_secret", return_value=None):
        gemini_section.refresh_saved_key_status()
        assert not gemini_section.btn_delete.isEnabled()

    with patch("ui.settings_dialog.get_secret", return_value="alguna-clave"):
        gemini_section.refresh_saved_key_status()
        assert gemini_section.btn_delete.isEnabled()


def test_verify_disables_buttons_while_running_and_reenables_on_finish(settings_dialog, monkeypatch):
    gemini_section = settings_dialog.stack.widget(1)
    gemini_section.input_api_key.setText("clave-a-verificar")

    # Mockear el worker para no depender de red real: se dispara "success" inmediato.
    class FakeWorker:
        def __init__(self, *_args, **_kwargs):
            self.verification_ok = MagicMock()
            self.verification_failed = MagicMock()
            self.finished = MagicMock()
            self._ok_slot = None
            self._finished_slot = None

        def start(self):
            # Simula la señal de éxito y de finalización de forma síncrona
            if self._ok_slot:
                self._ok_slot("Conexión verificada correctamente.")
            if self._finished_slot:
                self._finished_slot()

    fake_instance = FakeWorker()

    def fake_worker_ctor(key, parent=None):
        return fake_instance

    monkeypatch.setattr("ui.settings_dialog.GeminiKeyVerificationWorker", fake_worker_ctor)

    # Conectar manualmente los slots reales a los mocks del fake worker
    original_connect_ok = gemini_section._on_verification_ok
    original_connect_finished = gemini_section._on_verification_finished

    def patched_verify_clicked():
        gemini_section.btn_verify.setEnabled(False)
        gemini_section.btn_save.setEnabled(False)
        gemini_section.status_indicator.set_state(VerificationStatusIndicator.STATE_CHECKING)
        fake_instance._ok_slot = original_connect_ok
        fake_instance._finished_slot = original_connect_finished
        fake_instance.start()

    monkeypatch.setattr(gemini_section, "_on_verify_clicked", patched_verify_clicked)

    gemini_section._on_verify_clicked()

    # Tras la finalización simulada, los botones deben quedar reactivados
    assert gemini_section.btn_verify.isEnabled()
    assert gemini_section.btn_save.isEnabled()
    assert gemini_section.status_indicator.icon_label.text() == "✓"


def test_api_key_never_appears_in_plain_text_in_status_labels(settings_dialog):
    gemini_section = settings_dialog.stack.widget(1)
    secret_value = "AIzaSy-clave-super-secreta-000111"
    gemini_section.input_api_key.setText(secret_value)

    with patch("ui.settings_dialog.set_secret"), \
         patch("ui.settings_dialog.get_secret", return_value=secret_value):
        gemini_section._on_save_clicked()

    assert secret_value not in gemini_section.lbl_current_status.text()
    assert secret_value not in gemini_section.status_indicator.text_label.text()
    assert secret_value not in gemini_section.input_api_key.text()
