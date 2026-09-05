"""
Pruebas offscreen para AuditViewerScreen y AuditDetailsDialog (solo lectura).
Ejecutar con:
    QT_QPA_PLATFORM=offscreen python -m pytest ui/test_audit_viewer_screen.py -v

Verifica los requisitos funcionales de auditoría:
1. La pantalla renderiza sin excepciones con la tabla vacía y con datos de ejemplo.
2. El enmascarado de campos sensibles en details se aplica correctamente (api_key, token, password, secret).
3. El filtro por plugin_id y por resultado reduce las filas visibles sin perder los datos originales cargados.
4. No existe ningún control de escritura/borrado expuesto (tabla y acciones 100% de solo lectura).
"""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QPushButton

from core.audit_log import AuditLogger
from ui.app import JarvisMainWindow
from ui.audit_viewer_screen import (
    AuditDetailsDialog,
    AuditViewerDialog,
    AuditViewerScreen,
    mask_sensitive_data,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def empty_logger(tmp_path: Path):
    """Crea una base de datos SQLite aislada vacía."""
    db_path = tmp_path / "empty_audit.db"
    return AuditLogger(db_path=str(db_path))


@pytest.fixture
def populated_logger(tmp_path: Path):
    """Puebla el logger de auditoría con registros de ejemplo en base de datos aislada."""
    db_path = tmp_path / "populated_audit.db"
    logger = AuditLogger(db_path=str(db_path))
    logger.log_invocation(
        plugin_id="open_interpreter",
        action="search_files",
        capability="filesystem_read",
        allowed=True,
        result_status="éxito",
        details={"path": "/tmp/sandbox", "pattern": "*.py"},
    )
    logger.log_invocation(
        plugin_id="open_interpreter",
        action="run_python",
        capability="network_outbound",
        allowed=False,
        result_status="denegado",
        reason="Capacidad denegada por perfil",
        details={"code": "import socket; socket.connect()"},
    )
    logger.log_invocation(
        plugin_id="toy_plugin",
        action="ping",
        capability=None,
        allowed=True,
        result_status="éxito",
        details={"message": "hello"},
    )
    logger.log_invocation(
        plugin_id="custom_analyzer",
        action="fetch_data",
        capability="network_outbound",
        allowed=False,
        result_status="rate_limit",
        reason="Demasiadas peticiones",
        details={"endpoint": "https://api.example.com"},
    )
    return logger


def test_audit_viewer_renders_empty_and_with_sample_data(app, empty_logger, populated_logger):
    """
    Requisito 1: La pantalla renderiza sin excepciones con la tabla vacía y con datos de ejemplo.
    """
    # 1. Tabla vacía
    screen_empty = AuditViewerScreen(audit_logger=empty_logger)
    screen_empty.show()
    assert screen_empty.table.rowCount() == 0
    assert "0 de 0 registros" in screen_empty.lbl_record_count.text()
    screen_empty.close()

    # 2. Con datos poblados
    screen_populated = AuditViewerScreen(audit_logger=populated_logger)
    screen_populated.show()
    assert screen_populated.table.rowCount() == 4
    assert len(screen_populated._loaded_logs) == 4
    assert screen_populated.table.columnCount() == 5
    assert "4 de 4 registros" in screen_populated.lbl_record_count.text()

    # Verificar cabeceras
    expected_headers = ["Timestamp", "Plugin ID", "Acción", "Resultado", "Detalles"]
    actual_headers = [
        screen_populated.table.horizontalHeaderItem(i).text() for i in range(5)
    ]
    assert actual_headers == expected_headers
    screen_populated.close()


def test_sensitive_fields_masked_in_details(app):
    """
    Requisito 2: El enmascarado de campos sensibles en details se aplica correctamente
    (test con un registro simulado que tenga api_key, token, password, secret).
    """
    # A. Prueba unitaria de mask_sensitive_data
    sensitive_dict = {
        "user": "developer_1",
        "api_key": "SECRET_API_KEY_9999",
        "nested": {
            "oauth_token": "TOKEN_ABCDEF",
            "db_password": "super_secret_pwd",
            "client_secret": "xyz_secret",
            "safe_param": 42,
        },
        "tags": ["prod", "audit"],
    }

    masked = mask_sensitive_data(sensitive_dict)

    # Valores sensibles enmascarados
    assert masked["api_key"] == "***"
    assert masked["nested"]["oauth_token"] == "***"
    assert masked["nested"]["db_password"] == "***"
    assert masked["nested"]["client_secret"] == "***"

    # Valores no sensibles intactos
    assert masked["user"] == "developer_1"
    assert masked["nested"]["safe_param"] == 42
    assert masked["tags"] == ["prod", "audit"]

    # Soporte para JSON strings
    json_str = json.dumps(sensitive_dict)
    masked_from_str = mask_sensitive_data(json_str)
    assert masked_from_str["api_key"] == "***"

    # B. Prueba de interfaz con AuditDetailsDialog
    test_record = {
        "id": 101,
        "timestamp": "2026-09-04T02:00:00Z",
        "plugin_id": "test_plugin",
        "action": "login",
        "capability": "network_outbound",
        "allowed": 1,
        "result_status": "éxito",
        "reason": None,
        "details": json.dumps({"api_key": "EXPOSED_LEAK", "host": "auth.server.com"}),
    }

    dialog = AuditDetailsDialog(parent=None, record=test_record)
    dialog.show()

    displayed_text = dialog.txt_details.toPlainText()

    # 'EXPOSED_LEAK' NUNCA debe aparecer en pantalla
    assert "EXPOSED_LEAK" not in displayed_text
    # Debe contener '***' para el valor de api_key
    assert '"api_key": "***"' in displayed_text
    # Debe preservar el valor no sensible 'auth.server.com'
    assert "auth.server.com" in displayed_text

    dialog.close()


def test_client_side_filtering_by_plugin_id_and_result(app, populated_logger):
    """
    Requisito 3: El filtro por plugin_id y por resultado reduce las filas visibles
    sin perder los datos originales cargados.
    """
    screen = AuditViewerScreen(audit_logger=populated_logger)
    screen.show()

    # Estado inicial: 4 registros
    assert screen.table.rowCount() == 4
    assert len(screen._loaded_logs) == 4

    # 1. Filtrar por plugin_id = 'open_interpreter'
    idx_oi = screen.combo_plugin_id.findData("open_interpreter")
    assert idx_oi >= 0
    screen.combo_plugin_id.setCurrentIndex(idx_oi)

    # Solo deben verse 2 filas correspondientes a open_interpreter
    assert screen.table.rowCount() == 2
    for r in range(screen.table.rowCount()):
        assert screen.table.item(r, 1).text() == "open_interpreter"

    # Los datos originales cargados NO deben haberse reducido
    assert len(screen._loaded_logs) == 4

    # 2. Filtrar adicionalmente por resultado = 'denegado'
    idx_denied = screen.combo_result.findData("denegado")
    assert idx_denied >= 0
    screen.combo_result.setCurrentIndex(idx_denied)

    # Ahora solo 1 fila (open_interpreter con denegado)
    assert screen.table.rowCount() == 1
    assert screen.table.item(0, 1).text() == "open_interpreter"
    assert "denegado" in screen.table.item(0, 3).text()
    assert len(screen._loaded_logs) == 4

    # 3. Restablecer filtros a 'ALL'
    screen.combo_plugin_id.setCurrentIndex(screen.combo_plugin_id.findData("ALL"))
    screen.combo_result.setCurrentIndex(screen.combo_result.findData("ALL"))

    # Vuelve a mostrar todos los 4 registros originales
    assert screen.table.rowCount() == 4
    assert len(screen._loaded_logs) == 4

    screen.close()


def test_read_only_guarantee_no_write_or_delete_controls_exposed(app, populated_logger):
    """
    Requisito 4: Es de solo lectura: ningún botón debe permitir borrar o modificar
    registros de auditoría desde la UI (sin botones de delete/write).
    """
    screen = AuditViewerScreen(audit_logger=populated_logger)
    screen.show()

    # 1. La tabla debe tener deshabilitada la edición (NoEditTriggers)
    assert screen.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers

    # 2. Inspeccionar todos los botones de la pantalla
    buttons = screen.findChildren(QPushButton)
    prohibited_keywords = ["delete", "borrar", "eliminar", "clear", "vaciar", "drop", "update", "modificar"]

    for btn in buttons:
        btn_text = btn.text().lower()
        btn_name = btn.objectName().lower()
        for kw in prohibited_keywords:
            assert kw not in btn_text, f"Botón peligroso con texto '{btn.text()}' encontrado en AuditViewerScreen!"
            assert kw not in btn_name, f"Botón peligroso con ID '{btn.objectName()}' encontrado en AuditViewerScreen!"

    # 3. Ningún método propio de AuditViewerScreen debe realizar borrado o mutación
    own_methods = [
        name for name, val in AuditViewerScreen.__dict__.items()
        if callable(val) and not name.startswith("__")
    ]
    for m in own_methods:
        for kw in ["delete", "drop", "truncate", "remove_record", "purge", "clear_logs"]:
            assert kw not in m.lower(), f"Método sospechoso '{m}' encontrado en AuditViewerScreen!"

    screen.close()


def test_audit_button_in_main_window_header_opens_dialog(app, monkeypatch):
    """
    Verifica la integración en JarvisMainWindow: el botón con ícono 📜 en el header
    abre el diálogo modal de inspección de auditoría.
    """
    window = JarvisMainWindow()
    window.fps_timer.stop()
    window.audio_sim_timer.stop()
    window.show()

    assert hasattr(window, "btn_audit_logs")
    assert window.btn_audit_logs.text() == "📜"
    assert window.btn_audit_logs.objectName() == "audit_logs_btn"

    opened = False

    def mock_open_viewer(parent=None, audit_logger=None):
        nonlocal opened
        opened = True

    monkeypatch.setattr(AuditViewerDialog, "open_viewer", mock_open_viewer)

    window.btn_audit_logs.click()
    assert opened is True

    window.close()
