"""
Batería de pruebas unitarias y de integración para la Fase 1: Núcleo de JARVIS.
Cubre la matriz NUC-01 a NUC-06 con pytest.
"""

import sqlite3
from pathlib import Path
import pytest

from core.capability_catalog import (
    CAPABILITY_CATALOG,
    VALID_CAPABILITIES,
    validate_capabilities,
)
from core.version_profiles import VERSION_PROFILES, is_capability_allowed
from core.plugin_loader import PluginLoader
from core.dispatcher import Dispatcher
from core.audit_log import AuditLogger
from core.sandbox import (
    _SENSITIVE_SUBDIRS,
    resolve_sandbox_root,
    is_safe_path,
    register_authorized_root,
    reset_authorized_roots,
)


@pytest.fixture
def temp_audit_logger(tmp_path: Path) -> AuditLogger:
    """Fixture que crea un AuditLogger aislado en un directorio temporal."""
    db_file = tmp_path / "test_jarvis.db"
    return AuditLogger(db_path=db_file)


@pytest.fixture
def loader() -> PluginLoader:
    """Fixture que provee una instancia limpia de PluginLoader."""
    return PluginLoader()


# ============================================================================
# NUC-01: Manifiesto con capacidad fuera del catálogo → ValueError en la carga
# ============================================================================
def test_nuc_01_manifest_with_invalid_capability_raises_value_error(loader: PluginLoader):
    """
    NUC-01: Al cargar un manifiesto que declare una capacidad que no existe en
    el catálogo cerrado de capacidades, el cargador debe lanzar ValueError inmediatamente
    sin permitir que la acción llegue a registrarse o a invoke().
    """
    invalid_manifest = {
        "schema_version": "1",
        "id": "malicious_plugin",
        "name": "Malicious Plugin",
        "version": "1.0.0",
        "capabilities": ["system_info", "unauthorized_root_hack"],
        "actions": [
            {
                "name": "hack_system",
                "capability": "unauthorized_root_hack",
                "description": "Intento de registrar capacidad inexistente",
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        loader.parse_manifest_dict(invalid_manifest)

    assert "unauthorized_root_hack" in str(exc_info.value)
    assert "no reconocida en el catálogo cerrado" in str(exc_info.value)
    assert "malicious_plugin.hack_system" not in loader.registered_actions


# ============================================================================
# NUC-02: invoke() de capacidad no incluida en el perfil → {"ok": false, "reason": "capability_denied"}
# ============================================================================
def test_nuc_02_invoke_capability_not_in_version_profile_denied(
    loader: PluginLoader, temp_audit_logger: AuditLogger
):
    """
    NUC-02: Al invocar una acción cuya capacidad está fuera de lo autorizado
    por el perfil de versión activo (ej. filesystem_write en 'core_lite'), el dispatcher
    debe rechazar la llamada devolviendo {"ok": false, "reason": "capability_denied"}.
    """
    manifest_data = {
        "schema_version": "1",
        "id": "file_writer",
        "name": "File Writer Plugin",
        "version": "1.0.0",
        "capabilities": ["filesystem_write"],
        "actions": [
            {
                "name": "write_data",
                "capability": "filesystem_write",
                "description": "Escribe datos al disco",
            }
        ],
    }

    executed = False

    def dummy_writer(**kwargs):
        nonlocal executed
        executed = True
        return "written"

    loader.register_programmatic_plugin(manifest_data, handlers={"write_data": dummy_writer})

    # Usar perfil 'core_lite', el cual NO incluye 'filesystem_write'
    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_lite",
        audit_logger=temp_audit_logger,
    )

    result = dispatcher.invoke("file_writer.write_data", params={"file": "test.txt"})

    assert result["ok"] is False
    assert result["reason"] == "capability_denied"
    assert result["capability"] == "filesystem_write"
    assert executed is False  # La función nunca debió ejecutarse


# ============================================================================
# NUC-03: invoke() de capacidad con requires_confirmation, sin user_confirmed → {"ok": false, "reason": "needs_confirmation"}
# ============================================================================
def test_nuc_03_invoke_requires_confirmation_without_user_confirmed(
    loader: PluginLoader, temp_audit_logger: AuditLogger
):
    """
    NUC-03: Al invocar una acción con capacidad de riesgo (ej. code_execution) sin confirmación
    previa (user_confirmed=False), se rechaza con 'needs_confirmation'. Una vez confirmada,
    se cachea para la sesión de proceso y permite llamadas subsiguientes sin re-preguntar.
    """
    manifest_data = {
        "schema_version": "1",
        "id": "code_runner",
        "name": "Code Runner",
        "version": "1.0.0",
        "capabilities": ["code_execution"],
        "actions": [
            {
                "name": "run_snippet",
                "capability": "code_execution",
                "description": "Ejecuta snippet de código",
            }
        ],
    }

    def dummy_runner(code: str = ""):
        return f"result_of_{code}"

    loader.register_programmatic_plugin(manifest_data, handlers={"run_snippet": dummy_runner})

    # 'core_full' permite code_execution, pero code_execution requiere confirmación
    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_full",
        audit_logger=temp_audit_logger,
    )

    # 1. Llamada inicial sin confirmar -> rechazada con needs_confirmation
    res1 = dispatcher.invoke("code_runner.run_snippet", params={"code": "x=1"}, user_confirmed=False)
    assert res1["ok"] is False
    assert res1["reason"] == "needs_confirmation"
    assert res1["capability"] == "code_execution"

    # 2. Llamada con confirmación explícita -> ejecutada y cacheada en sesión
    res2 = dispatcher.invoke("code_runner.run_snippet", params={"code": "x=1"}, user_confirmed=True)
    assert res2["ok"] is True
    assert res2["result"] == "result_of_x=1"

    # 3. Siguiente llamada en la misma sesión sin user_confirmed=True -> debe pasar por estar cacheada
    res3 = dispatcher.invoke("code_runner.run_snippet", params={"code": "y=2"}, user_confirmed=False)
    assert res3["ok"] is True
    assert res3["result"] == "result_of_y=2"

    # 4. Al reiniciar la sesión, debe volver a exigir confirmación
    dispatcher.reset_session_confirmations()
    res4 = dispatcher.invoke("code_runner.run_snippet", params={"code": "z=3"}, user_confirmed=False)
    assert res4["ok"] is False
    assert res4["reason"] == "needs_confirmation"


# ============================================================================
# NUC-04: Plugin pasa sandbox_root como ruta libre ("/etc") → el núcleo lo ignora
# ============================================================================
def test_nuc_04_sandbox_root_ignores_free_path_and_resolves_fixed(tmp_path: Path):
    """
    NUC-04: Si un plugin o llamador intenta pasar una ruta libre arbitraria como
    sandbox_root (ej. '/etc' o '/root'), el núcleo la ignora y resuelve estrictamente
    hacia las raíces autorizadas fijas.
    Además, _SENSITIVE_SUBDIRS y allowlist por defecto protegen directorios y archivos
    críticos (.env, credentials.json, .ssh, etc.) incluso sin especificar allowed_extensions.
    """
    workspace = tmp_path / "safe_workspace"
    workspace.mkdir()
    register_authorized_root("workspace", workspace)
    register_authorized_root("default", workspace)

    # 1. Intento de pasar '/etc' como ruta libre
    resolved = resolve_sandbox_root("/etc")
    assert resolved == workspace.resolve()
    assert resolved != Path("/etc").resolve()

    # 2. is_safe_path() permite archivos seguros con allowlist por defecto
    assert is_safe_path(workspace / "valid.txt", sandbox_root=workspace) is True
    assert is_safe_path(workspace / "script.py", sandbox_root=workspace) is True
    assert is_safe_path("/etc/passwd", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "../escaped.txt", sandbox_root=workspace) is False

    # 3. Subdirectorios sensibles estructurales (_SENSITIVE_SUBDIRS) bloqueados
    for sensitive in [".ssh", ".aws", ".gnupg", ".docker", ".kube", ".password-store"]:
        sensitive_path = workspace / sensitive / "id_rsa"
        assert is_safe_path(sensitive_path, sandbox_root=workspace) is False

    # 4. Archivos de secretos/credenciales bloqueados DENTRO del sandbox sin pasar allowed_extensions
    assert is_safe_path(workspace / ".env", sandbox_root=workspace) is False
    assert is_safe_path(workspace / ".env.production", sandbox_root=workspace) is False
    assert is_safe_path(workspace / ".env.local", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "credentials.json", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "credentials_prod.json", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "my_credentials.json", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "subdir" / ".env", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "nested" / "credentials.json", sandbox_root=workspace) is False

    # 5. Aislamiento de nombre sensible con extensiones SÍ permitidas (.txt, .py, .md)
    assert is_safe_path(workspace / "my_credentials.txt", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "id_rsa_backup.py", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "notes_credentials.md", sandbox_root=workspace) is False
    assert is_safe_path(workspace / "meeting_notes.txt", sandbox_root=workspace) is True  # Caso de control


def test_sandbox_root_independent_of_process_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Verifica que cambiar el cwd del proceso NO altera la raíz del sandbox
    cuando se define explícitamente vía JARVIS_SANDBOX_ROOT o configuración.
    """
    from core.sandbox import set_default_sandbox_root

    explicit_root = tmp_path / "explicit_sandbox_root"
    other_cwd = tmp_path / "completely_unrelated_dir"
    explicit_root.mkdir()
    other_cwd.mkdir()

    # Limpiar custom root previo y configurar variable de entorno explícita
    set_default_sandbox_root(None)
    monkeypatch.setenv("JARVIS_SANDBOX_ROOT", str(explicit_root))
    reset_authorized_roots()

    # Cambiar cwd del proceso a otro directorio
    monkeypatch.chdir(other_cwd)

    resolved = resolve_sandbox_root()
    assert resolved == explicit_root.resolve()
    assert resolved != other_cwd.resolve()


def test_sandbox_root_default_repo_root_independent_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    Verifica que sin JARVIS_SANDBOX_ROOT seteada ni config programática,
    la raíz por defecto es _REPO_ROOT (calculada desde __file__) y cambiar el
    cwd con monkeypatch.chdir() NO altera la raíz resuelta.
    """
    from core.sandbox import _REPO_ROOT, get_default_sandbox_base, set_default_sandbox_root

    # Asegurar que no hay variable de entorno ni custom root activo
    monkeypatch.delenv("JARVIS_SANDBOX_ROOT", raising=False)
    set_default_sandbox_root(None)
    reset_authorized_roots()

    # Raíz esperada es _REPO_ROOT
    assert get_default_sandbox_base() == _REPO_ROOT.resolve()
    assert resolve_sandbox_root() == _REPO_ROOT.resolve()

    # Cambiar cwd a un directorio temporal cualquiera
    other_dir = tmp_path / "somewhere_else"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    # La raíz resuelta sigue siendo _REPO_ROOT y NO el nuevo cwd
    assert resolve_sandbox_root() == _REPO_ROOT.resolve()
    assert resolve_sandbox_root() != other_dir.resolve()


# ============================================================================
# NUC-05: Cualquier invoke() (permitido o denegado) → fila nueva en SQLite
# ============================================================================
def test_nuc_05_every_invoke_persists_to_audit_logs_sqlite(
    loader: PluginLoader, tmp_path: Path
):
    """
    NUC-05: Todo invoke() — permitido, denegado por perfil, bloqueado por confirmación
    o con error de ejecución — genera una fila en la tabla 'audit_logs' de SQLite,
    verificable mediante una consulta SQL real.
    """
    db_file = tmp_path / "audit_test.db"
    audit_logger = AuditLogger(db_path=db_file)

    manifest_data = {
        "schema_version": "1",
        "id": "toy",
        "name": "Toy Plugin",
        "version": "1.0.0",
        "capabilities": ["system_info"],
        "actions": [
            {
                "name": "get_time",
                "capability": "system_info",
                "description": "Devuelve la hora",
            }
        ],
    }
    loader.register_programmatic_plugin(
        manifest_data,
        handlers={"get_time": lambda: "12:00:00"},
    )

    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_lite",
        audit_logger=audit_logger,
    )

    # 1. Invocación permitida exitosa
    dispatcher.invoke("toy.get_time")

    # 2. Invocación de acción inexistente (denegada)
    dispatcher.invoke("toy.non_existent_action")

    # Verificar directamente en SQLite con una consulta SQL real
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT plugin_id, action, allowed, result_status FROM audit_logs ORDER BY id ASC"
        ).fetchall()

    assert len(rows) == 2
    # Registro 1: éxito
    assert rows[0][0] == "toy"
    assert rows[0][1] == "get_time"
    assert rows[0][2] == 1  # allowed = True
    assert rows[0][3] == "success"

    # Registro 2: denegado
    assert rows[1][0] == "toy"
    assert rows[1][1] == "non_existent_action"
    assert rows[1][2] == 0  # allowed = False
    assert rows[1][3] == "denied"


# ============================================================================
# NUC-06: Dos plugins con acción de igual nombre → ambos cargan sin colisión
# ============================================================================
def test_nuc_06_two_plugins_same_action_name_no_collision(
    loader: PluginLoader, temp_audit_logger: AuditLogger
):
    """
    NUC-06: Dos plugins distintos pueden declarar una acción con el mismo nombre (ej. 'get_status')
    sin ninguna colisión, ya que el motor las registra y las invoca exclusivamente mediante el
    namespace 'plugin_id.action_name'.
    """
    manifest_a = {
        "schema_version": "1",
        "id": "sensor_a",
        "name": "Sensor A",
        "version": "1.0.0",
        "capabilities": ["system_info"],
        "actions": [
            {
                "name": "get_status",
                "capability": "system_info",
                "description": "Estado de Sensor A",
            }
        ],
    }

    manifest_b = {
        "schema_version": "1",
        "id": "sensor_b",
        "name": "Sensor B",
        "version": "1.0.0",
        "capabilities": ["system_info"],
        "actions": [
            {
                "name": "get_status",
                "capability": "system_info",
                "description": "Estado de Sensor B",
            }
        ],
    }

    loader.register_programmatic_plugin(
        manifest_a,
        handlers={"get_status": lambda: "status_from_sensor_A"},
    )
    loader.register_programmatic_plugin(
        manifest_b,
        handlers={"get_status": lambda: "status_from_sensor_B"},
    )

    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_lite",
        audit_logger=temp_audit_logger,
    )

    res_a = dispatcher.invoke("sensor_a.get_status")
    res_b = dispatcher.invoke("sensor_b.get_status")

    assert res_a["ok"] is True
    assert res_a["result"] == "status_from_sensor_A"

    assert res_b["ok"] is True
    assert res_b["result"] == "status_from_sensor_B"

    assert "sensor_a.get_status" in loader.registered_actions
    assert "sensor_b.get_status" in loader.registered_actions
