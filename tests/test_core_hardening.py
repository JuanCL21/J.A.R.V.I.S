"""
Tests de seguridad y robustez arquitectónica para:
- core/secrets.py (creación atómica con 0600 sin ventana de exposición)
- core/audit_log.py (independencia de cwd, inicialización lazy y sin efectos en import)
- core/logging_setup.py (resolución de directorio contra _REPO_ROOT)
"""

import os
from pathlib import Path
import stat
import pytest

from core.secrets import get_secret, set_secret, load_secrets
from core.audit_log import AuditLogger, get_default_audit_logger, default_audit_logger
from core.plugin_registry import _DEFAULT_DB_PATH, _REPO_ROOT
from core.logging_setup import resolve_log_dir, _DEFAULT_LOG_DIR


def test_secrets_adversarial_no_permission_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    TEST REQUERIDO 1:
    Verifica que en ningún punto del proceso el archivo de secretos queda con
    permisos distintos de 0600 (sin ventana de exposición de lectura bajo umask del sistema).
    """
    env_file = tmp_path / "subdir" / ".env"
    captured_modes = []

    real_os_open = os.open

    def wrapped_os_open(path, flags, mode=0o777, **kwargs):
        # Capturar la llamada a os.open
        fd = real_os_open(path, flags, mode, **kwargs)
        if Path(path).resolve() == env_file.resolve():
            st = os.fstat(fd)
            # Registrar el modo del descriptor en el instante exacto de apertura/creación
            captured_modes.append((flags, mode, stat.S_IMODE(st.st_mode)))
        return fd

    monkeypatch.setattr(os, "open", wrapped_os_open)

    # Establecer umask permisiva para probar que os.open(..., 0o600) no hereda permisos de lectura grupales/otros
    old_umask = os.umask(0o022)
    try:
        set_secret("API_KEY", "super_secret_token_xyz", env_path=env_file)
    finally:
        os.umask(old_umask)

    assert len(captured_modes) >= 1
    flags, requested_mode, actual_descriptor_mode = captured_modes[0]

    # Verificar que se solicitó O_CREAT y modo 0o600
    assert flags & os.O_CREAT, "os.open debe incluir O_CREAT"
    assert requested_mode == 0o600, "El modo solicitado en os.open debe ser 0o600"
    # Verificar que el descriptor nació con permisos 0o600 exactos
    assert actual_descriptor_mode == 0o600, "El descriptor debe nacer con 0600 en el filesystem"

    # Verificar que el archivo en disco mantiene 0600 y el secreto fue persistido
    file_mode = stat.S_IMODE(os.stat(env_file).st_mode)
    assert file_mode == 0o600, "El archivo final debe tener permisos 0600"
    assert get_secret("API_KEY", env_path=env_file) == "super_secret_token_xyz"

    # Actualizar secreto existente y verificar que no se alteran los permisos
    set_secret("DB_PASSWORD", "another_secret", env_path=env_file)
    updated_mode = stat.S_IMODE(os.stat(env_file).st_mode)
    assert updated_mode == 0o600
    assert get_secret("DB_PASSWORD", env_path=env_file) == "another_secret"
    assert get_secret("API_KEY", env_path=env_file) == "super_secret_token_xyz"


def test_audit_log_db_path_independent_of_process_cwd_and_no_spurious_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    TEST REQUERIDO 2:
    Replicar para audit_log.py el mismo test que ya existe para plugin_registry.py:
    1. Instanciar sin db_path desde dos cwd diferentes resuelve exactamente la misma ruta canónica (_REPO_ROOT).
    2. Instanciar la clase (sin invocar operaciones que abran conexión) NO crea archivos de base de datos
       ni directorios espurios en el cwd actual (lazy initialization).
    3. Anulación explícita vía JARVIS_DB_PATH soportada.
    4. La base de datos y tabla audit_logs se crean limpiamente en la primera operación real.
    """
    dir_1 = tmp_path / "audit_cwd_1"
    dir_2 = tmp_path / "audit_cwd_2"
    dir_1.mkdir()
    dir_2.mkdir()

    # Asegurar que no haya anulación por variable de entorno
    monkeypatch.delenv("JARVIS_DB_PATH", raising=False)

    # --- CWD 1 ---
    monkeypatch.chdir(dir_1)
    logger_1 = AuditLogger()

    # La ruta resuelta debe ser la canónica del repositorio (_REPO_ROOT / database / jarvis.db)
    assert logger_1.db_path == _DEFAULT_DB_PATH.resolve()
    assert logger_1.db_path != (dir_1 / "database" / "jarvis.db").resolve()

    # Verificar que NO se crearon archivos en dir_1 por solo instanciar
    assert not (dir_1 / "database").exists(), "No debe crearse carpeta database en el cwd"
    assert not (dir_1 / "jarvis.db").exists(), "No debe crearse jarvis.db en el cwd"
    assert list(dir_1.iterdir()) == [], "El cwd actual debe permanecer completamente limpio"

    # --- CWD 2 ---
    monkeypatch.chdir(dir_2)
    logger_2 = AuditLogger()

    # La ruta resuelta en cwd 2 debe ser EXACTAMENTE idéntica a la de cwd 1
    assert logger_2.db_path == logger_1.db_path
    assert logger_2.db_path == _DEFAULT_DB_PATH.resolve()
    assert logger_2.db_path != (dir_2 / "database" / "jarvis.db").resolve()

    # Verificar que NO se crearon archivos en dir_2
    assert list(dir_2.iterdir()) == [], "El cwd actual 2 debe permanecer completamente limpio"

    # --- Variable de entorno JARVIS_DB_PATH (anulación explícita) ---
    custom_db_dir = tmp_path / "env_custom_audit"
    custom_db_file = custom_db_dir / "custom_jarvis.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(custom_db_file))

    logger_env = AuditLogger()
    assert logger_env.db_path == custom_db_file.resolve()

    # La instanciación NO debe haber creado la carpeta ni el archivo aún
    assert not custom_db_dir.exists(), "La instanciación no debe crear directorios en disco"
    assert not custom_db_file.exists(), "La instanciación no debe crear el archivo SQLite"

    # Operación real: log_invocation debe crear el directorio, esquema y persistir
    row_id = logger_env.log_invocation(
        plugin_id="toy",
        action="echo",
        capability=None,
        allowed=True,
        result_status="success",
        reason=None,
        details={"params": {"msg": "hello audit"}},
    )
    assert row_id > 0
    assert custom_db_file.exists(), "La primera operación real debe crear la base de datos"

    # Consultar logs persistidos
    logs = logger_env.query_logs(plugin_id="toy")
    assert len(logs) == 1
    assert logs[0]["action"] == "echo"
    assert logs[0]["allowed"] == 1
    assert "hello audit" in logs[0]["details"]


def test_audit_log_default_logger_lazy_access():
    """Verifica que default_audit_logger sea accesible de manera perezosa sin romper compatibilidad."""
    logger = get_default_audit_logger()
    assert isinstance(logger, AuditLogger)
    assert default_audit_logger.db_path == _DEFAULT_DB_PATH.resolve()


def test_logging_setup_dir_independent_of_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    FIX 3 TEST:
    Verifica que resolve_log_dir resuelva contra _REPO_ROOT y nunca contra os.getcwd().
    """
    dir_1 = tmp_path / "log_cwd_1"
    dir_2 = tmp_path / "log_cwd_2"
    dir_1.mkdir()
    dir_2.mkdir()

    monkeypatch.delenv("JARVIS_LOG_DIR", raising=False)

    # En dir_1: resolución por defecto debe ser _REPO_ROOT / logs
    monkeypatch.chdir(dir_1)
    res_1 = resolve_log_dir("logs")
    assert res_1 == _DEFAULT_LOG_DIR.resolve()
    assert res_1 != (dir_1 / "logs").resolve()

    # En dir_2: exactamente la misma ruta canónica
    monkeypatch.chdir(dir_2)
    res_2 = resolve_log_dir("logs")
    assert res_2 == res_1

    # Subdirectorio relativo dado explícitamente se resuelve contra _REPO_ROOT
    res_rel = resolve_log_dir("my_custom_logs")
    assert res_rel == (_REPO_ROOT / "my_custom_logs").resolve()
    assert res_rel != (dir_2 / "my_custom_logs").resolve()

    # Ruta absoluta se respeta
    abs_dir = (tmp_path / "absolute_logs").resolve()
    assert resolve_log_dir(abs_dir) == abs_dir

    # log_dir=None retorna None
    assert resolve_log_dir(None) is None

    # Variable de entorno JARVIS_LOG_DIR
    monkeypatch.setenv("JARVIS_LOG_DIR", str(abs_dir))
    assert resolve_log_dir("logs") == abs_dir
