"""
Batería de pruebas adversariales para la Fase 4: Plugin Open Interpreter.
Cubre la matriz OI-01 a OI-07 con pytest pensando como atacante.
"""

import os
from pathlib import Path
import pytest

from core.audit_log import AuditLogger
from core.dispatcher import Dispatcher
from core.plugin_loader import PluginLoader
from core.sandbox import reset_authorized_roots, set_default_sandbox_root
from plugins.open_interpreter.plugin import DEFAULT_RUN_TIMEOUT

OI_PLUGIN_DIR = Path(__file__).parent.parent / "plugins" / "open_interpreter"


@pytest.fixture
def isolated_env(tmp_path: Path):
    """Configura un sandbox y base de datos de auditoría aislados para pruebas de Open Interpreter."""
    sandbox_dir = tmp_path / "oi_sandbox"
    sandbox_dir.mkdir()
    set_default_sandbox_root(sandbox_dir)
    reset_authorized_roots()

    audit_db = tmp_path / "oi_audit.db"
    audit_logger = AuditLogger(db_path=audit_db)

    loader = PluginLoader(audit_logger=audit_logger)
    loaded = loader.load(OI_PLUGIN_DIR, version_profile="core_full")
    assert loaded is True, "El plugin open_interpreter debe cargar bajo el perfil 'core_full'"

    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_full",
        audit_logger=audit_logger,
    )

    yield {
        "sandbox": sandbox_dir,
        "dispatcher": dispatcher,
        "loader": loader,
        "audit_logger": audit_logger,
    }

    set_default_sandbox_root(None)
    reset_authorized_roots()


# ============================================================================
# OI-01: run_python con intento de ataque / conexión de red → aislamiento de SO
# ============================================================================
def test_oi_01_run_python_adversarial_network_and_os_isolation(isolated_env):
    """
    OI-01: Intento de abrir un socket de red externo o ejecutar comandos host.
    Verifica si corre con Bubblewrap (bwrap) aislando la red (Network unreachable).
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]

    # Payload adversarial: intento de conexión externa a internet
    net_payload = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2.0)
s.connect(('1.1.1.1', 80))
"""
    res = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": net_payload, "timeout": 5.0},
        user_confirmed=True,
    )

    assert res["ok"] is True
    run_res = res["result"]
    # El backend detectado debe ser 'bwrap' o 'subprocess'
    assert run_res["backend"] in ("bwrap", "subprocess")

    if run_res["backend"] == "bwrap":
        # Con bwrap, la red está deshabilitada (--unshare-net)
        assert run_res["ok"] is False
        assert run_res["returncode"] != 0
        assert "Network is unreachable" in run_res["stderr"] or "Errno 101" in run_res["stderr"]


# ============================================================================
# OI-02: write_file con path traversal hacia .ssh/id_rsa → rechazado
# ============================================================================
def test_oi_02_write_file_path_traversal_rejected(isolated_env):
    """
    OI-02: Intento de escapar del sandbox para escribir una clave SSH vía path traversal.
    Debe ser bloqueado antes de tocar el disco.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]
    sandbox: Path = isolated_env["sandbox"]

    traversal_path = "../../.ssh/id_rsa"
    res = dispatcher.invoke(
        "open_interpreter.write_file",
        params={"path": traversal_path, "content": "MALICIOUS_KEY"},
        user_confirmed=True,
    )

    assert res["ok"] is False
    assert res["reason"] == "execution_error"
    assert "PermissionError" in res["error"] or "rechazada por el sandbox" in res["error"]

    # Confirmar que ningún archivo fue creado fuera del sandbox
    assert not (sandbox.parent.parent / ".ssh" / "id_rsa").exists()


# ============================================================================
# OI-03: write_file con nombres sensibles (.env*, *credentials*) → rechazados + caso de control
# ============================================================================
def test_oi_03_write_file_sensitive_names_variants_and_control(isolated_env):
    """
    OI-03: Batería adversarial completa contra nombres sensibles:
    - credentials.json
    - credentials_prod.json
    - my_credentials.json
    - .env.production
    - .env.local
    - my_credentials.txt (con extensión permitida)
    Todos deben ser RECHAZADOS.
    Caso de control inocuo (meeting_notes.txt) debe ser ACEPTADO.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]
    sandbox: Path = isolated_env["sandbox"]

    malicious_filenames = [
        "credentials.json",
        "credentials_prod.json",
        "my_credentials.json",
        ".env.production",
        ".env.local",
        "my_credentials.txt",
    ]

    for filename in malicious_filenames:
        res = dispatcher.invoke(
            "open_interpreter.write_file",
            params={"path": filename, "content": "SECRET_DATA=123"},
            user_confirmed=True,
        )
        assert res["ok"] is False, f"El archivo sensible '{filename}' debió ser rechazado"
        assert res["reason"] == "execution_error"
        assert not (sandbox / filename).exists()

    # Caso de control: archivo inocuo con extensión permitida
    control_res = dispatcher.invoke(
        "open_interpreter.write_file",
        params={"path": "meeting_notes.txt", "content": "Notas de la reunión"},
        user_confirmed=True,
    )
    assert control_res["ok"] is True
    assert (sandbox / "meeting_notes.txt").exists()
    assert (sandbox / "meeting_notes.txt").read_text(encoding="utf-8") == "Notas de la reunión"


# ============================================================================
# OI-04: create_presentation con path injection → python-pptx seguro
# ============================================================================
def test_oi_04_create_presentation_structured_data_and_path_safety(isolated_env):
    """
    OI-04: create_presentation solo consume datos estructurados vía python-pptx,
    pasa allowed_extensions=['.pptx'] y rechaza rutas externas.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]
    sandbox: Path = isolated_env["sandbox"]

    # 1. Intento de path traversal con extensión no permitida o escape
    bad_res = dispatcher.invoke(
        "open_interpreter.create_presentation",
        params={
            "path": "../../escaped.pptx",
            "slides": [{"title": "Hack", "content": "Payload"}],
        },
        user_confirmed=True,
    )
    assert bad_res["ok"] is False
    assert bad_res["reason"] == "execution_error"

    # 2. Creación legítima con extensión .pptx y datos estructurados
    slides_data = [
        {"title": "Diapositiva 1", "bullets": ["Punto A", "Punto B"]},
        {"title": "Diapositiva 2", "content": "Texto descriptivo"},
    ]
    good_res = dispatcher.invoke(
        "open_interpreter.create_presentation",
        params={
            "path": "resumen_proyecto.pptx",
            "slides": slides_data,
            "title": "Informe Q3",
        },
        user_confirmed=True,
    )
    assert good_res["ok"] is True
    assert good_res["result"]["slides_count"] == 3
    assert (sandbox / "resumen_proyecto.pptx").exists()
    assert (sandbox / "resumen_proyecto.pptx").stat().st_size > 0


# ============================================================================
# OI-05: search_local_files con intento de escape → acotado a sandbox_root
# ============================================================================
def test_oi_05_search_local_files_confined_to_sandbox(isolated_env):
    """
    OI-05: search_local_files con patrones '*/../*' o subfolder '../'
    permanece confinado al sandbox_root sin escapar ni lanzar excepciones.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]
    sandbox: Path = isolated_env["sandbox"]

    # Crear archivos dentro del sandbox
    (sandbox / "doc1.txt").write_text("doc1", encoding="utf-8")
    (sandbox / "sub").mkdir()
    (sandbox / "sub" / "doc2.txt").write_text("doc2", encoding="utf-8")

    # 1. Intento de escape mediante patrón
    res1 = dispatcher.invoke(
        "open_interpreter.search_local_files",
        params={"pattern": "*"},
        user_confirmed=True,
    )
    assert res1["ok"] is True
    matches = res1["result"]["matches"]
    assert "doc1.txt" in matches
    assert "sub/doc2.txt" in matches or "sub" in matches

    # 2. Intento de escape con '..' en subfolder
    res2 = dispatcher.invoke(
        "open_interpreter.search_local_files",
        params={"subfolder": "../../", "pattern": "*"},
        user_confirmed=True,
    )
    assert res2["ok"] is True
    # La búsqueda debe seguir contenida en sandbox_root
    assert res2["result"]["base_directory"] == str(sandbox.resolve())


# ============================================================================
# OI-06: run_python sin user_confirmed → needs_confirmation y confirmación de sesión
# ============================================================================
def test_oi_06_run_python_confirmation_and_session_caching(isolated_env):
    """
    OI-06:
    1. run_python sin confirmación previa es bloqueado con reason: 'needs_confirmation'.
    2. Confirmar con user_confirmed=True ejecuta la acción y cachea la capacidad
       para el resto de la sesión de proceso.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]

    # 1. Invocación sin confirmar -> bloqueada
    res_unconfirmed = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": "print('hello')"},
        user_confirmed=False,
    )
    assert res_unconfirmed["ok"] is False
    assert res_unconfirmed["reason"] == "needs_confirmation"
    assert res_unconfirmed["capability"] == "code_execution"

    # 2. Confirmación explícita -> ejecutada y cacheada
    res_confirmed = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": "print('hello_confirmed')"},
        user_confirmed=True,
    )
    assert res_confirmed["ok"] is True
    assert "hello_confirmed" in res_confirmed["result"]["stdout"]

    # 3. Siguiente invocación en la misma sesión sin user_confirmed -> permitida automáticamente
    res_subsequent = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": "print('hello_session')"},
        user_confirmed=False,
    )
    assert res_subsequent["ok"] is True
    assert "hello_session" in res_subsequent["result"]["stdout"]


# ============================================================================
# OI-07: run_python con bucle infinito → cancelado por timeout
# ============================================================================
def test_oi_07_run_python_infinite_loop_timeout(isolated_env):
    """
    OI-07: run_python con script en bucle infinito (while True: pass)
    se cancela por timeout. El valor de timeout por defecto configurado es 10.0s.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]
    assert DEFAULT_RUN_TIMEOUT == 10.0

    infinite_loop_code = "while True: pass"
    res = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": infinite_loop_code, "timeout": 1.0},
        user_confirmed=True,
    )

    assert res["ok"] is True
    run_res = res["result"]
    assert run_res["ok"] is False
    assert run_res["reason"] == "timeout"
    assert "timeout de 1.0s" in run_res["error"]


# ============================================================================
# OI-08: run_python sin bwrap en el sistema → rechazo fail-closed
# ============================================================================
def test_oi_08_run_python_fail_closed_without_bwrap(isolated_env, monkeypatch):
    """
    OI-08: Política fail-closed: Si bwrap no está instalado en el sistema operativo
    (shutil.which('bwrap') devuelve None), run_python RECHAZA la ejecución de código
    con un error explícito en lugar de degradar silenciosamente a un subprocess sin aislamiento.
    """
    from plugins.open_interpreter.plugin import run_python

    # 1. Simular ausencia de bwrap en el sistema operativo
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    # Invocación directa debe lanzar RuntimeError fail-closed
    with pytest.raises(RuntimeError, match="fail-closed"):
        run_python("print('esto no debe ejecutarse')")

    # Invocación a través del Dispatcher debe devolver ok=False con execution_error
    dispatcher: Dispatcher = isolated_env["dispatcher"]
    res = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": "print('esto no debe ejecutarse')"},
        user_confirmed=True,
    )
    assert res["ok"] is False
    assert res["reason"] == "execution_error"
    assert "Aislamiento de red no disponible" in res["error"]
    assert "fail-closed" in res["error"]


# ============================================================================
# TESTS ADVERSARIALES REQUERIDOS (FIX 1 y FIX 2)
# ============================================================================

def test_search_local_files_adversarial_double_dot_bypass_rejected(isolated_env):
    """
    TEST ADVERSARIAL REQUERIDO 1:
    Verifica que patrones como '....//', '....//....//', '../' y variantes que burlaban
    la sanitización simple (.replace('../', '')) sean rechazados de raíz por la nueva
    validación por resolución de rutas (Path.resolve() e is_relative_to()).
    Garantiza que ningún archivo fuera del sandbox_root (ej. señuelo en directorio padre)
    sea expuesto o retornado en 'matches'.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]
    sandbox: Path = isolated_env["sandbox"]

    # 1. Crear archivo señuelo sensible fuera del sandbox (en el directorio padre)
    outside_file = sandbox.parent / "leak_secret.txt"
    outside_file.write_text("SUPER_SECRET_LEAK=9999", encoding="utf-8")

    # Crear archivo legítimo dentro del sandbox
    (sandbox / "legitimate.txt").write_text("Contenido legítimo", encoding="utf-8")

    # Batería de patrones diseñados para escapar mediante secuencias de doble punto
    bypass_patterns = [
        "....//",
        "....//....//",
        "....//*",
        "....//....//*",
        "....//leak_secret.txt",
        "..../....//leak_secret.txt",
        "../",
        "../../",
        "../*",
        "../../leak_secret.txt",
    ]

    for bad_pattern in bypass_patterns:
        res = dispatcher.invoke(
            "open_interpreter.search_local_files",
            params={"pattern": bad_pattern},
            user_confirmed=True,
        )
        # La invocación debe ser rechazada con execution_error por PermissionError
        assert res["ok"] is False, f"El patrón adversarial '{bad_pattern}' debió ser rechazado"
        assert res["reason"] == "execution_error"
        assert "Búsqueda rechazada por el sandbox" in res["error"] or "PermissionError" in res["error"]

    # Caso de control: búsqueda legítima con patrón normal funciona y confina
    control_res = dispatcher.invoke(
        "open_interpreter.search_local_files",
        params={"pattern": "*.txt"},
        user_confirmed=True,
    )
    assert control_res["ok"] is True
    matches = control_res["result"]["matches"]
    assert "legitimate.txt" in matches
    assert not any("leak_secret" in m for m in matches)


def test_run_python_bwrap_reduced_surface_isolates_etc_and_proc(isolated_env):
    """
    TEST ADVERSARIAL REQUERIDO 2:
    Verifica la reducción de superficie en Bubblewrap (bwrap):
    1. /etc ya no se expone completo: lectura de /etc/passwd falla con FileNotFoundError.
    2. /proc está aislado en un namespace de PID privado (--unshare-pid): los cientos de PIDs
       del host no son visibles; únicamente se observan los procesos internos del sandbox.
    3. Código Python estándar (math, datetime, json, etc.) sigue ejecutándose sin problemas.
    """
    dispatcher: Dispatcher = isolated_env["dispatcher"]

    # 1. Probar que /etc/passwd no es accesible
    etc_code = """
try:
    with open('/etc/passwd', 'r') as f:
        print('LEAKED:' + f.read()[:50])
except FileNotFoundError:
    print('PROTECTED_ETC_PASSWD_NOT_FOUND')
"""
    res_etc = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": etc_code},
        user_confirmed=True,
    )
    assert res_etc["ok"] is True
    assert "PROTECTED_ETC_PASSWD_NOT_FOUND" in res_etc["result"]["stdout"]
    assert "LEAKED" not in res_etc["result"]["stdout"]

    # 2. Probar que el namespace de PID está aislado (no ve los cientos de procesos del host)
    proc_code = """
import os
pids = [p for p in os.listdir('/proc') if p.isdigit()]
print(f'VISIBLE_PIDS_COUNT:{len(pids)}')
"""
    res_proc = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": proc_code},
        user_confirmed=True,
    )
    assert res_proc["ok"] is True
    stdout_proc = res_proc["result"]["stdout"]
    assert "VISIBLE_PIDS_COUNT:" in stdout_proc
    count_str = stdout_proc.split("VISIBLE_PIDS_COUNT:")[1].strip()
    visible_count = int(count_str)
    assert visible_count <= 5, f"Esperado <= 5 PIDs en namespace aislado, se encontraron {visible_count}"

    # 3. Probar que código Python estándar funciona normalmente
    std_code = """
import math, json, datetime
data = {"pi": math.pi, "timestamp": datetime.datetime.now().isoformat()}
print("COMPUTED:" + json.dumps(data))
"""
    res_std = dispatcher.invoke(
        "open_interpreter.run_python",
        params={"code": std_code},
        user_confirmed=True,
    )
    assert res_std["ok"] is True
    assert res_std["result"]["ok"] is True
    assert "COMPUTED:" in res_std["result"]["stdout"]


