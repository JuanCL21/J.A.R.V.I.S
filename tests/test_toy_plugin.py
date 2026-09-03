"""
Batería de pruebas unitarias y de integración para la Fase 2: Plugin de Juguete (Toy Plugin).
Cubre la matriz TOY-01 a TOY-03 con pytest.
"""

from pathlib import Path
import pytest

from core.audit_log import AuditLogger
from core.dispatcher import Dispatcher
from core.plugin_loader import PluginLoader
from core.version_profiles import register_profile

TOY_PLUGIN_DIR = Path(__file__).parent.parent / "plugins" / "toy"


@pytest.fixture
def temp_audit_logger(tmp_path: Path) -> AuditLogger:
    """Crea una base de datos de auditoría aislada para pruebas."""
    return AuditLogger(db_path=tmp_path / "toy_audit.db")


# ============================================================================
# Ejecución básica end-to-end del Toy Plugin
# ============================================================================
def test_toy_plugin_basic_execution(temp_audit_logger: AuditLogger):
    """Prueba que el plugin toy carga desde disco y ejecuta get_time correctamente."""
    loader = PluginLoader()
    loaded = loader.load(TOY_PLUGIN_DIR, version_profile="core_lite")
    assert loaded is True
    assert "toy" in loader.loaded_plugins
    assert "toy.get_time" in loader.registered_actions

    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_lite",
        audit_logger=temp_audit_logger,
    )

    response = dispatcher.invoke("toy.get_time")
    assert response["ok"] is True
    assert "result" in response
    assert "iso" in response["result"]
    assert "formatted" in response["result"]


# ============================================================================
# TOY-01: Invocar acción no declarada en el manifiesto → reason: "action_not_declared"
# ============================================================================
def test_toy_01_invoke_undeclared_action_returns_action_not_declared(
    temp_audit_logger: AuditLogger,
):
    """
    TOY-01: Al invocar una acción que no está declarada en el manifiesto del plugin toy,
    el núcleo debe rechazarla explícitamente con reason: 'action_not_declared'.
    """
    loader = PluginLoader()
    loader.load(TOY_PLUGIN_DIR, version_profile="core_lite")

    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile="core_lite",
        audit_logger=temp_audit_logger,
    )

    # Invocamos una acción inventada que no figura en manifest.json
    res = dispatcher.invoke("toy.undeclared_action_xyz", params={"param": 123})

    assert res["ok"] is False
    assert res["reason"] == "action_not_declared"
    assert res["action"] == "toy.undeclared_action_xyz"


# ============================================================================
# TOY-02: Cargar el toy plugin contra un perfil sin su capacidad → load() devuelve False
# ============================================================================
def test_toy_02_load_against_profile_without_capability_returns_false():
    """
    TOY-02: Si intentamos cargar el plugin toy contra un perfil de versión que NO incluye
    su capacidad requerida ('system_info'), load() devuelve False y el plugin NO queda
    en el registro de cargados (loaded_plugins) ni en registered_actions.
    """
    # Registramos un perfil restringido que solo permite 'filesystem_read', NO 'system_info'
    register_profile("restricted_filesystem_only", ["filesystem_read"])

    loader = PluginLoader()
    loaded = loader.load(TOY_PLUGIN_DIR, version_profile="restricted_filesystem_only")

    assert loaded is False
    assert "toy" not in loader.loaded_plugins
    assert "toy.get_time" not in loader.registered_actions


# ============================================================================
# TOY-03: Reiniciar el proceso → el plugin recarga limpio, sin estado previo
# ============================================================================
def test_toy_03_restarting_process_reloads_clean(temp_audit_logger: AuditLogger):
    """
    TOY-03: Al simular un reinicio de proceso (instanciando un nuevo PluginLoader y Dispatcher),
    el plugin se recarga desde disco de manera limpia, sin retener estado o cachés de la corrida previa.
    """
    # Proceso / Corrida 1
    loader_run_1 = PluginLoader()
    loader_run_1.load(TOY_PLUGIN_DIR, version_profile="core_lite")
    dispatcher_run_1 = Dispatcher(
        plugin_loader=loader_run_1,
        version_profile="core_lite",
        audit_logger=temp_audit_logger,
    )
    # Confirmar una capacidad para mutar el estado en memoria de la corrida 1
    dispatcher_run_1.session_confirmed_capabilities.add("code_execution")
    res_1 = dispatcher_run_1.invoke("toy.get_time")
    assert res_1["ok"] is True

    # Proceso / Corrida 2 (Reinicio)
    loader_run_2 = PluginLoader()
    loader_run_2.load(TOY_PLUGIN_DIR, version_profile="core_lite")
    dispatcher_run_2 = Dispatcher(
        plugin_loader=loader_run_2,
        version_profile="core_lite",
        audit_logger=temp_audit_logger,
    )

    # Verificar que el nuevo proceso está completamente limpio
    assert len(dispatcher_run_2.session_confirmed_capabilities) == 0
    assert "code_execution" not in dispatcher_run_2.session_confirmed_capabilities

    res_2 = dispatcher_run_2.invoke("toy.get_time")
    assert res_2["ok"] is True
    assert "iso" in res_2["result"]
