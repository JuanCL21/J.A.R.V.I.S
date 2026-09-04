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
        "is_curated": True,
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


# ============================================================================
# TESTS ADVERSARIALES: Aislamiento de confirmaciones y no-reintento de TypeError
# ============================================================================
def test_dispatcher_adversarial_confirmation_not_shared_across_plugins(
    loader: PluginLoader, temp_audit_logger: AuditLogger
):
    """
    Test adversarial 1: Confirmar una capacidad para plugin_id='plugin_a' NO debe autorizar
    en silencio la misma capacidad para plugin_id='plugin_b' en la misma sesión.
    Si la caché no incluye plugin_id, este test falla.
    """
    manifest_a = {
        "schema_version": "1",
        "id": "plugin_a",
        "name": "Plugin A",
        "version": "1.0.0",
        "capabilities": ["filesystem_write"],
        "is_curated": True,
        "actions": [
            {
                "name": "write_data",
                "capability": "filesystem_write",
                "description": "Escribe datos A",
            }
        ],
    }
    manifest_b = {
        "schema_version": "1",
        "id": "plugin_b",
        "name": "Plugin B",
        "version": "1.0.0",
        "capabilities": ["filesystem_write"],
        "actions": [
            {
                "name": "write_data",
                "capability": "filesystem_write",
                "description": "Escribe datos B",
            }
        ],
    }

    loader.register_programmatic_plugin(
        manifest_a, handlers={"write_data": lambda **kw: "written_a"}
    )
    loader.register_programmatic_plugin(
        manifest_b, handlers={"write_data": lambda **kw: "written_b"}
    )

    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_full",
        audit_logger=temp_audit_logger,
    )

    # 1. Confirmar capacidad para plugin_a en la sesión
    res_a1 = dispatcher.invoke(
        "plugin_a.write_data",
        params={"content": "hello_a"},
        user_confirmed=True,
        session_id="session_alpha",
    )
    assert res_a1["ok"] is True
    assert res_a1["result"] == "written_a"

    # 2. Invocación subsecuente para plugin_a en la misma sesión -> permitida por caché
    res_a2 = dispatcher.invoke(
        "plugin_a.write_data",
        params={"content": "hello_a2"},
        user_confirmed=False,
        session_id="session_alpha",
    )
    assert res_a2["ok"] is True
    assert res_a2["result"] == "written_a"

    # 3. Invocar la MISMA capacidad desde plugin_b en la MISMA sesión sin user_confirmed
    # DEBE exigir confirmación de nuevo (rechazada con needs_confirmation)
    res_b = dispatcher.invoke(
        "plugin_b.write_data",
        params={"content": "malicious_payload_b"},
        user_confirmed=False,
        session_id="session_alpha",
    )
    assert res_b["ok"] is False
    assert res_b["reason"] == "needs_confirmation"
    assert res_b["capability"] == "filesystem_write"

    # 4. Probar reseteo específico de sesión sin afectar otras sesiones
    res_a_beta = dispatcher.invoke(
        "plugin_a.write_data",
        params={"content": "hello_beta"},
        user_confirmed=True,
        session_id="session_beta",
    )
    assert res_a_beta["ok"] is True

    # Resetear solo session_alpha
    dispatcher.reset_session_confirmations(session_id="session_alpha")
    # session_alpha vuelve a exigir confirmación
    res_a_alpha_after = dispatcher.invoke(
        "plugin_a.write_data",
        params={"content": "hello_alpha3"},
        user_confirmed=False,
        session_id="session_alpha",
    )
    assert res_a_alpha_after["ok"] is False
    assert res_a_alpha_after["reason"] == "needs_confirmation"

    # session_beta permanece cacheada
    res_a_beta_after = dispatcher.invoke(
        "plugin_a.write_data",
        params={"content": "hello_beta2"},
        user_confirmed=False,
        session_id="session_beta",
    )
    assert res_a_beta_after["ok"] is True


def test_dispatcher_adversarial_handler_typeerror_executes_only_once(
    loader: PluginLoader, temp_audit_logger: AuditLogger
):
    """
    Test adversarial 2: Un handler que cuenta cuántas veces fue invocado y lanza
    TypeError intencionalmente en su lógica interna (no por firma incorrecta)
    debe ejecutarse EXACTAMENTE 1 vez, nunca 2 veces.
    """
    manifest = {
        "schema_version": "1",
        "id": "buggy_plugin",
        "name": "Buggy Plugin",
        "version": "1.0.0",
        "capabilities": ["system_info"],
        "actions": [
            {
                "name": "faulty_action",
                "capability": "system_info",
                "description": "Lanza TypeError interno",
            }
        ],
    }

    call_count = 0

    def faulty_handler(val: str = "default"):
        nonlocal call_count
        call_count += 1
        # Simular TypeError interno dentro de la lógica del plugin (ej. suma inválida)
        return "prefix_" + 12345  # type: ignore

    loader.register_programmatic_plugin(
        manifest, handlers={"faulty_action": faulty_handler}
    )

    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_full",
        audit_logger=temp_audit_logger,
    )

    res = dispatcher.invoke("buggy_plugin.faulty_action", params={"val": "test"})

    assert res["ok"] is False
    assert res["reason"] == "execution_error"
    assert "TypeError" in res.get("error", "") or "concatenate" in res.get("error", "")
    assert call_count == 1, f"El handler se ejecutó {call_count} veces (debe ser exactamente 1)"


def test_dispatcher_adversarial_unregistered_or_unverified_plugin_ignores_cache(
    loader: PluginLoader, temp_audit_logger: AuditLogger, tmp_path: Path
):
    """
    Test adversarial: Un plugin no registrado o con status='no_verificado'
    NUNCA usa la caché de confirmación por sesión, sin importar qué otro
    plugin ya haya confirmado esa capacidad.
    """
    from core.plugin_registry import PluginRegistry

    db_path = tmp_path / "test_unverified_cache.db"
    reg = PluginRegistry(db_path=db_path)

    # 1. Plugin curado (ej. plugin_trusted)
    reg.register_plugin("plugin_trusted", "a" * 40, "https://local/trusted")
    reg.promote_to_curated("plugin_trusted", "auditor_test")

    # 2. Plugin no verificado (status='no_verificado')
    reg.register_plugin("plugin_unverified", "b" * 40, "https://local/unverified")

    # 3. Registrar los 3 plugins en el loader
    manifest_trusted = {
        "schema_version": "1",
        "id": "plugin_trusted",
        "name": "Trusted Plugin",
        "version": "1.0.0",
        "capabilities": ["filesystem_write"],
        "actions": [{"name": "write", "capability": "filesystem_write"}],
    }
    manifest_unverified = {
        "schema_version": "1",
        "id": "plugin_unverified",
        "name": "Unverified Plugin",
        "version": "1.0.0",
        "capabilities": ["filesystem_write"],
        "actions": [{"name": "write", "capability": "filesystem_write"}],
    }
    manifest_unregistered = {
        "schema_version": "1",
        "id": "plugin_unregistered",
        "name": "Unregistered Plugin",
        "version": "1.0.0",
        "capabilities": ["filesystem_write"],
        "actions": [{"name": "write", "capability": "filesystem_write"}],
    }

    loader_inst = PluginLoader(audit_logger=temp_audit_logger, plugin_registry=reg)
    loader_inst.register_programmatic_plugin(
        manifest_trusted, handlers={"write": lambda **kw: "trusted_written"}
    )
    loader_inst.register_programmatic_plugin(
        manifest_unverified, handlers={"write": lambda **kw: "unverified_written"}
    )
    loader_inst.register_programmatic_plugin(
        manifest_unregistered, handlers={"write": lambda **kw: "unregistered_written"}
    )

    dispatcher = Dispatcher(
        plugin_loader=loader_inst,
        version_profile="core_full",
        audit_logger=temp_audit_logger,
        plugin_registry=reg,
    )

    session = "sess_adversarial"

    # Paso A: Confirmar para plugin_trusted -> debe ejecutarse y cachearse
    res_t1 = dispatcher.invoke(
        "plugin_trusted.write",
        params={"f": "1"},
        user_confirmed=True,
        session_id=session,
    )
    assert res_t1["ok"] is True
    # Invocación subsecuente para plugin_trusted pasa por caché
    res_t2 = dispatcher.invoke(
        "plugin_trusted.write",
        params={"f": "2"},
        user_confirmed=False,
        session_id=session,
    )
    assert res_t2["ok"] is True

    # Paso B: Invocación en plugin_unverified con confirmación explícita -> ejecuta pero NO cachea
    res_uv1 = dispatcher.invoke(
        "plugin_unverified.write",
        params={"f": "3"},
        user_confirmed=True,
        session_id=session,
    )
    assert res_uv1["ok"] is True
    assert res_uv1["result"] == "unverified_written"

    # Invocación subsecuente en plugin_unverified sin confirmación en la MISMA sesión:
    # NUNCA debe usar la caché; debe volver a exigir confirmación
    res_uv2 = dispatcher.invoke(
        "plugin_unverified.write",
        params={"f": "4"},
        user_confirmed=False,
        session_id=session,
    )
    assert res_uv2["ok"] is False
    assert res_uv2["reason"] == "needs_confirmation"

    # Paso C: Invocación en plugin_unregistered (no existe en registro):
    # Ejecuta con user_confirmed=True pero NO cachea
    res_ur1 = dispatcher.invoke(
        "plugin_unregistered.write",
        params={"f": "5"},
        user_confirmed=True,
        session_id=session,
    )
    assert res_ur1["ok"] is True
    assert res_ur1["result"] == "unregistered_written"

    # Invocación subsecuente en plugin_unregistered sin confirmación en la MISMA sesión:
    # NUNCA debe usar la caché; debe volver a exigir confirmación
    res_ur2 = dispatcher.invoke(
        "plugin_unregistered.write",
        params={"f": "6"},
        user_confirmed=False,
        session_id=session,
    )
    assert res_ur2["ok"] is False
    assert res_ur2["reason"] == "needs_confirmation"


def test_sandbox_directory_operations_allowed_with_empty_suffix(tmp_path: Path):
    """
    TEST REQUERIDO 3:
    FIX 2 (a): Operaciones sobre directorios con sufijo vacío permitidas
    explícitamente cuando allow_directory=True o is_directory=True,
    sin forzar extensiones de archivo falsas ni permitir escape del sandbox.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    register_authorized_root("workspace", workspace)
    register_authorized_root("default", workspace)

    try:
        sub_dir = workspace / "reports_folder"
        sub_dir.mkdir()

        # 1. Modo directorio explícito permite sufijo vacío
        assert is_safe_path(sub_dir, sandbox_root=workspace, allow_directory=True) is True
        assert is_safe_path(sub_dir, sandbox_root=workspace, is_directory=True) is True

        # 2. Rutas aún no creadas en disco pero con intención de ser directorios
        uncreated_dir = workspace / "future_folder"
        assert is_safe_path(uncreated_dir, sandbox_root=workspace, allow_directory=True) is True

        # 3. Modo archivo por defecto (allow_directory=False) rechaza sufijo vacío
        assert is_safe_path(sub_dir, sandbox_root=workspace, allow_directory=False) is False
        assert is_safe_path(sub_dir, sandbox_root=workspace) is False

        # 4. Directorios sensibles siguen bloqueados incluso con allow_directory=True
        assert is_safe_path(workspace / ".git", sandbox_root=workspace, allow_directory=True) is False
        assert is_safe_path(workspace / ".ssh", sandbox_root=workspace, allow_directory=True) is False
        assert is_safe_path(workspace / "credentials", sandbox_root=workspace, allow_directory=True) is False

        # 5. Escape de sandbox sigue bloqueado en modo directorio
        assert is_safe_path(tmp_path / "escaped_folder", sandbox_root=workspace, allow_directory=True) is False
    finally:
        reset_authorized_roots()


def test_sandbox_path_component_matching_no_false_positive(tmp_path: Path):
    """
    TEST REQUERIDO 4:
    FIX 2 (b): Coincidencia de componentes de ruta exactos (Path.parts).
    Evita falsos positivos por substrings libres en nombres de directorios
    legítimos como 'digital_art/' (que contiene 'git') o 'mi_credentials_guide/'
    (que contiene 'credentials').
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    register_authorized_root("workspace", workspace)
    register_authorized_root("default", workspace)

    try:
        # 1. Carpeta con substring 'git' (ej. digital_art) no bloquea archivos ni el directorio
        art_dir = workspace / "digital_art"
        art_dir.mkdir()
        art_file = art_dir / "design.png"
        assert is_safe_path(art_file, sandbox_root=workspace) is True
        assert is_safe_path(art_dir, sandbox_root=workspace, allow_directory=True) is True

        # 2. Carpeta con substring 'credentials' (ej. mi_credentials_guide) no bloquea archivos ni el directorio
        guide_dir = workspace / "mi_credentials_guide"
        guide_dir.mkdir()
        guide_file = guide_dir / "architecture.md"
        assert is_safe_path(guide_file, sandbox_root=workspace) is True
        assert is_safe_path(guide_dir, sandbox_root=workspace, allow_directory=True) is True

        # 3. Carpeta con substring 'ssh' (ej. ssh_guide) no bloquea archivos
        ssh_notes = workspace / "ssh_guide" / "readme.txt"
        assert is_safe_path(ssh_notes, sandbox_root=workspace) is True

        # 4. Contraprueba: componentes que coinciden exactamente con directorios sensibles SÍ son bloqueados
        assert is_safe_path(workspace / ".git" / "config", sandbox_root=workspace) is False
        assert is_safe_path(workspace / ".ssh" / "id_rsa", sandbox_root=workspace) is False
        assert is_safe_path(workspace / "credentials" / "data.txt", sandbox_root=workspace) is False
        assert is_safe_path(workspace / ".config" / "google-chrome" / "Default", sandbox_root=workspace, allow_directory=True) is False
    finally:
        reset_authorized_roots()


def test_sandbox_still_blocks_original_jarvis_custom_vulnerability(tmp_path: Path):
    """
    TEST REQUERIDO 5 (NO REGRESIÓN):
    Verifica que la vulnerabilidad original de JARVIS_Custom (burlar la protección
    de credenciales mediante nombres de archivo como credentials.json,
    credentials_prod.json, my_credentials.txt) SIGA bloqueada fail-closed mediante
    coincidencia de patrones en el nombre de archivo (filename).
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    register_authorized_root("workspace", workspace)
    register_authorized_root("default", workspace)

    try:
        sensitive_files = [
            "credentials.json",
            "credentials_prod.json",
            "my_credentials.json",
            "my_credentials.txt",
            "notes_credentials.md",
            ".env",
            ".env.production",
            ".env.local",
            "id_rsa_backup.py",
            "id_ed25519_key.txt",
        ]

        for s_file in sensitive_files:
            assert is_safe_path(workspace / s_file, sandbox_root=workspace) is False, (
                f"Fallo de seguridad: '{s_file}' debió ser bloqueado estructuralmente"
            )
    finally:
        reset_authorized_roots()




