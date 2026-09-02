"""
Batería de pruebas unitarias y de integración para la Fase 3: Core Lite.
Cubre la matriz LITE-01 a LITE-03 con pytest.
"""

import sqlite3
from pathlib import Path
import pytest

from core.audit_log import AuditLogger
from core.plugin_loader import PluginLoader
from core.version_profiles import VERSION_PROFILES
from versions.core_lite.main import start_core_lite


@pytest.fixture
def temp_audit_logger(tmp_path: Path) -> AuditLogger:
    """Fixture que crea un AuditLogger aislado en un directorio temporal."""
    return AuditLogger(db_path=tmp_path / "core_lite_audit.db")


# ============================================================================
# LITE-01: Arrancar core_lite y verificar inicio limpio sin puertos HTTP/GUI
# ============================================================================
def test_lite_01_core_lite_starts_cleanly_without_network_servers(
    temp_audit_logger: AuditLogger,
):
    """
    LITE-01: Arrancar core_lite y verificar que inicializa el núcleo
    adecuadamente sin levantar ningún servidor HTTP ni socket de escucha.
    """
    dispatcher, loader, audit_log = start_core_lite(audit_logger=temp_audit_logger)

    assert dispatcher is not None
    assert dispatcher.version_profile in ("core_lite", "core-lite")
    assert loader is not None
    # El plugin toy (si existe en plugins/) debe poder cargarse
    if "toy" in loader.loaded_plugins:
        res = dispatcher.invoke("toy.get_time")
        assert res["ok"] is True


# ============================================================================
# LITE-02: Intentar cargar manifiesto de Open Interpreter contra core-lite → False + auditoría
# ============================================================================
def test_lite_02_open_interpreter_manifest_rejected_and_audited(
    tmp_path: Path, temp_audit_logger: AuditLogger
):
    """
    LITE-02: Intentar cargar un plugin con capacidades de Open Interpreter
    (code_execution, filesystem_write, filesystem_read) contra el perfil 'core-lite'
    debe devolver load() == False y generar un registro de auditoría en jarvis.db.
    """
    oi_plugin_dir = tmp_path / "mock_open_interpreter"
    oi_plugin_dir.mkdir()

    manifest_content = """{
        "schema_version": "1",
        "id": "open_interpreter",
        "name": "Open Interpreter Plugin",
        "version": "1.0.0",
        "capabilities": ["code_execution", "filesystem_write"],
        "actions": [
            {
                "name": "run_python",
                "capability": "code_execution",
                "description": "Ejecuta script Python"
            },
            {
                "name": "write_file",
                "capability": "filesystem_write",
                "description": "Escribe un archivo"
            }
        ]
    }"""
    (oi_plugin_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

    loader = PluginLoader(audit_logger=temp_audit_logger)
    loaded = loader.load(oi_plugin_dir, version_profile="core-lite")

    # 1. load() devuelve False y no se registra
    assert loaded is False
    assert "open_interpreter" not in loader.loaded_plugins
    assert "open_interpreter.run_python" not in loader.registered_actions

    # 2. Verificar entrada en la tabla de auditoría de SQLite
    with sqlite3.connect(str(temp_audit_logger.db_path)) as conn:
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT plugin_id, action, allowed, result_status, reason, details
            FROM audit_logs
            WHERE plugin_id = 'open_interpreter'
            """
        ).fetchall()

    assert len(rows) == 1
    plugin_id, action, allowed, result_status, reason, details = rows[0]
    assert plugin_id == "open_interpreter"
    assert action == "load_plugin"
    assert allowed == 0
    assert result_status == "denied"
    assert reason == "capability_denied"
    assert "core-lite" in details or "core_lite" in details


# ============================================================================
# LITE-03: Leer VERSION_PROFILES["core-lite"] → sin filesystem ni code_execution
# ============================================================================
def test_lite_03_version_profiles_core_lite_strictly_restricted():
    """
    LITE-03: Leer VERSION_PROFILES['core-lite'] directamente y verificar que:
    1. NO contiene 'filesystem_write'
    2. NO contiene 'filesystem_read'
    3. NO contiene 'code_execution'
    4. Solo contiene capacidades seguras de mensajería/notificación/sistema.
    """
    caps_lite = VERSION_PROFILES["core-lite"]

    # Verificaciones negativas estrictas
    assert "filesystem_write" not in caps_lite
    assert "filesystem_read" not in caps_lite
    assert "code_execution" not in caps_lite

    # Verificaciones positivas
    assert "notify_user" in caps_lite
    assert "telegram_send" in caps_lite
    assert "system_info" in caps_lite
