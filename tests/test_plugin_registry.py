"""
Pruebas de la Subfase A: Modelo de datos plugin_registry y correcciones de seguridad.
Cubre:
1. Creación y estructura de la tabla plugin_registry en SQLite.
2. Separación estricta entre active_commit_hash y candidate_commit_hash.
3. Test requerido: crear plugin con commit A curado, simular detección de commit B,
   verificar que active_commit_hash sigue en A y B queda solo en candidate_commit_hash.
4. Unidad de confianza como par (plugin_id, commit_hash) — un commit nuevo no hereda status curado.
5. FIX PROBLEMA 1: register_plugin inserta SIEMPRE no_verificado, sin posibilidad de bypass.
6. FIX PROBLEMA 2: Resolución canónica de la ruta de DB independiente de os.getcwd() y sin
   creación espuria de archivos en instanciación.
"""

import os
from pathlib import Path
import sqlite3
import pytest

from core.plugin_registry import PluginRegistry, _REPO_ROOT, _DEFAULT_DB_PATH


@pytest.fixture
def registry(tmp_path: Path) -> PluginRegistry:
    """Instancia de PluginRegistry sobre base de datos aislada en tmp_path."""
    db_path = tmp_path / "test_jarvis.db"
    return PluginRegistry(db_path=db_path)


def test_subfase_a_plugin_registry_table_structure(registry: PluginRegistry):
    """Verifica que la tabla plugin_registry contenga las columnas y restricciones requeridas."""
    conn = registry._get_connection()
    try:
        cursor = conn.execute("PRAGMA table_info(plugin_registry)")
        columns = {row["name"]: row["type"] for row in cursor.fetchall()}

        expected_columns = [
            "plugin_id",
            "active_commit_hash",
            "candidate_commit_hash",
            "status",
            "source_url",
            "reviewed_by",
            "reviewed_at",
            "promoted_at",
        ]

        for col in expected_columns:
            assert col in columns, f"Columna '{col}' no encontrada en tabla plugin_registry"

        # Verificar restricción CHECK de status
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(
                    """
                    INSERT INTO plugin_registry (
                        plugin_id, active_commit_hash, status, source_url
                    ) VALUES ('test_p', 'c123', 'invalido', 'https://github.com/test/repo')
                    """
                )
    finally:
        conn.close()


def test_subfase_a_required_detection_separation_active_vs_candidate(registry: PluginRegistry):
    """
    TEST REQUERIDO SUBFASE A:
    Crear plugin con commit A curado, simular detección de commit B,
    verificar que active_commit_hash sigue en A y B queda solo en candidate_commit_hash.
    """
    plugin_id = "sample_plugin"
    commit_a = "a1b2c3d4e5f67890123456789abcdef012345678"
    commit_b = "b9c8d7e6f5a43210987654321fedcba98765432"
    source_url = "https://github.com/org/sample_plugin.git"

    # 1. Registrar plugin (se crea siempre como no_verificado) y luego promoverlo explícitamente a curado
    registry.register_plugin(
        plugin_id=plugin_id,
        active_commit_hash=commit_a,
        source_url=source_url,
    )
    promoted = registry.promote_to_curated(
        plugin_id=plugin_id,
        reviewed_by="auditor_principal",
        reviewed_at="2026-09-02T22:00:00Z",
        promoted_at="2026-09-02T22:05:00Z",
    )
    assert promoted is True

    initial_state = registry.get_plugin(plugin_id)
    assert initial_state is not None
    assert initial_state["active_commit_hash"] == commit_a
    assert initial_state["candidate_commit_hash"] is None
    assert initial_state["status"] == "curado"
    assert initial_state["reviewed_by"] == "auditor_principal"

    # 2. Simular detección de nuevo commit B en repositorio remoto
    success = registry.set_candidate_commit(plugin_id, candidate_commit_hash=commit_b)
    assert success is True

    # 3. Verificar que active_commit_hash SIGUE en A y B queda SOLO en candidate_commit_hash
    updated_state = registry.get_plugin(plugin_id)
    assert updated_state is not None
    assert updated_state["active_commit_hash"] == commit_a, (
        "REGLA CRÍTICA VIOLADA: active_commit_hash fue modificado por la detección"
    )
    assert updated_state["candidate_commit_hash"] == commit_b, (
        "candidate_commit_hash debe contener el commit detectado B"
    )
    assert updated_state["status"] == "curado", (
        "El estado curado del commit A en ejecución debe preservarse intacto tras la detección"
    )


def test_subfase_a_trust_unit_is_pair_plugin_id_and_commit_hash(registry: PluginRegistry):
    """
    Verifica que la unidad de confianza sea el PAR (plugin_id, commit_hash).
    Un commit nuevo del mismo plugin_id NUNCA hereda el status del commit anterior.
    """
    plugin_id = "trusted_plugin"
    commit_a = "1111111111111111111111111111111111111111"
    commit_b = "2222222222222222222222222222222222222222"

    registry.register_plugin(
        plugin_id=plugin_id,
        active_commit_hash=commit_a,
        source_url="https://github.com/org/trusted.git",
    )
    registry.promote_to_curated(
        plugin_id=plugin_id,
        reviewed_by="auditor_seguridad",
    )

    # El par (trusted_plugin, commit_a) es curado
    assert registry.is_curated(plugin_id, commit_hash=commit_a) is True

    # El par (trusted_plugin, commit_b) NO es curado aunque sea el mismo plugin_id
    assert registry.is_curated(plugin_id, commit_hash=commit_b) is False

    # Simular detección y aplicación de actualización a commit B
    registry.set_candidate_commit(plugin_id, commit_b)
    applied = registry.apply_candidate_update(plugin_id)
    assert applied is True

    # Tras aplicar la actualización, active_commit_hash es B pero el status DEBE ser no_verificado
    after_update = registry.get_plugin(plugin_id)
    assert after_update["active_commit_hash"] == commit_b
    assert after_update["candidate_commit_hash"] is None
    assert after_update["status"] == "no_verificado", (
        "REGLA CRÍTICA VIOLADA: Un commit nuevo nunca puede heredar el status curado anterior"
    )
    assert after_update["reviewed_by"] is None
    assert registry.is_curated(plugin_id, commit_hash=commit_b) is False


def test_register_plugin_strictly_enforces_no_verificado_and_no_metadata_bypass(registry: PluginRegistry):
    """
    TEST REQUERIDO (PROBLEMA 1):
    Verifica que register_plugin no admita parámetros para alterar el status ni auditoría.
    Cualquier inserción o actualización vía register_plugin DEBE resultar estrictamente
    en status='no_verificado' y reviewed_by/reviewed_at/promoted_at en None.
    """
    plugin_id = "bypass_attempt_plugin"
    commit_1 = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
    source_url = "https://github.com/org/bypass.git"

    # 1. Intentar pasar parámetros prohibidos (status, reviewed_by, etc.) debe fallar a nivel de signatura
    with pytest.raises(TypeError):
        registry.register_plugin(  # type: ignore
            plugin_id=plugin_id,
            active_commit_hash=commit_1,
            source_url=source_url,
            status="curado",
        )

    with pytest.raises(TypeError):
        registry.register_plugin(  # type: ignore
            plugin_id=plugin_id,
            active_commit_hash=commit_1,
            source_url=source_url,
            reviewed_by="admin_malicioso",
        )

    # 2. Invocación normal legítima
    registry.register_plugin(
        plugin_id=plugin_id,
        active_commit_hash=commit_1,
        source_url=source_url,
    )

    entry = registry.get_plugin(plugin_id)
    assert entry is not None
    assert entry["status"] == "no_verificado", "El status debe ser forzosamente no_verificado"
    assert entry["reviewed_by"] is None, "reviewed_by debe ser forzosamente None"
    assert entry["reviewed_at"] is None, "reviewed_at debe ser forzosamente None"
    assert entry["promoted_at"] is None, "promoted_at debe ser forzosamente None"
    assert registry.is_curated(plugin_id) is False

    # 3. Promoverlo a curado mediante la ÚNICA vía autorizada
    registry.promote_to_curated(plugin_id, reviewed_by="auditor_oficial")
    assert registry.is_curated(plugin_id) is True

    # 4. Volver a registrar el plugin (ej. actualización de commit directo):
    # Debe RESETEAR forzosamente el status a no_verificado y limpiar metadatos de auditoría
    commit_2 = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
    registry.register_plugin(
        plugin_id=plugin_id,
        active_commit_hash=commit_2,
        source_url=source_url,
    )

    re_registered = registry.get_plugin(plugin_id)
    assert re_registered is not None
    assert re_registered["active_commit_hash"] == commit_2
    assert re_registered["status"] == "no_verificado", (
        "Llamar a register_plugin jamás debe preservar status curado"
    )
    assert re_registered["reviewed_by"] is None
    assert re_registered["reviewed_at"] is None
    assert re_registered["promoted_at"] is None
    assert registry.is_curated(plugin_id) is False


def test_plugin_registry_db_path_independent_of_process_cwd_and_no_spurious_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    TEST REQUERIDO (PROBLEMA 2):
    1. Instanciar sin db_path desde dos cwd diferentes resuelve exactamente la misma ruta canónica (_REPO_ROOT).
    2. Instanciar la clase (sin invocar operaciones que abran conexión) NO crea archivos de base de datos
       ni directorios espurios en el cwd actual.
    """
    dir_1 = tmp_path / "cwd_workdir_1"
    dir_2 = tmp_path / "cwd_workdir_2"
    dir_1.mkdir()
    dir_2.mkdir()

    # Asegurar que no haya anulación por variable de entorno
    monkeypatch.delenv("JARVIS_DB_PATH", raising=False)

    # --- CWD 1 ---
    monkeypatch.chdir(dir_1)
    reg_1 = PluginRegistry()

    # La ruta resuelta debe ser la canónica del repositorio (_REPO_ROOT / database / jarvis.db)
    assert reg_1.db_path == _DEFAULT_DB_PATH.resolve()
    assert reg_1.db_path != (dir_1 / "database" / "jarvis.db").resolve()

    # Verificar que NO se crearon archivos en dir_1 por solo instanciar
    assert not (dir_1 / "database").exists(), "No debe crearse carpeta database en el cwd"
    assert not (dir_1 / "jarvis.db").exists(), "No debe crearse jarvis.db en el cwd"
    assert list(dir_1.iterdir()) == [], "El cwd actual debe permanecer completamente limpio"

    # --- CWD 2 ---
    monkeypatch.chdir(dir_2)
    reg_2 = PluginRegistry()

    # La ruta resuelta en cwd 2 debe ser EXACTAMENTE idéntica a la de cwd 1
    assert reg_2.db_path == reg_1.db_path
    assert reg_2.db_path == _DEFAULT_DB_PATH.resolve()
    assert reg_2.db_path != (dir_2 / "database" / "jarvis.db").resolve()

    # Verificar que NO se crearon archivos en dir_2
    assert list(dir_2.iterdir()) == [], "El cwd actual 2 debe permanecer completamente limpio"

    # --- Variable de entorno JARVIS_DB_PATH (anulación explícita) ---
    custom_db_dir = tmp_path / "env_custom_location"
    custom_db_file = custom_db_dir / "custom_jarvis.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(custom_db_file))

    reg_env = PluginRegistry()
    assert reg_env.db_path == custom_db_file.resolve()

    # La instanciación NO debe haber creado aún el archivo
    assert not custom_db_file.exists(), "La instanciación no debe crear el archivo de base de datos"

    # Al invocar una operación que requiere conexión, se inicializa perezosamente (lazy)
    assert reg_env.list_plugins() == []
    assert custom_db_file.exists(), "El archivo de DB debe crearse solo cuando se requiere conexión"


# ============================================================================
# TEST REQUERIDO: Migración de plugins de primera parte con fechas reales de Git
# ============================================================================
def test_migration_toy_and_open_interpreter_curated_with_real_dates(tmp_path: Path):
    """
    Verifica que la migración de plugins de primera parte (toy y open_interpreter)
    los registre en plugin_registry y los promueva a status='curado' con los
    commit hashes y fechas históricas reales de git log.
    """
    import subprocess
    from core.plugin_registry import FIRST_PARTY_PLUGINS, migrate_first_party_plugins

    db_path = tmp_path / "test_migration.db"
    reg = PluginRegistry(db_path=db_path)
    migrate_first_party_plugins(reg)

    toy = reg.get_plugin("toy")
    assert toy is not None
    assert toy["status"] == "curado"
    assert toy["reviewed_by"] == "aprobado en Fase 2 (TOY-01 a TOY-03)"

    oi = reg.get_plugin("open_interpreter")
    assert oi is not None
    assert oi["status"] == "curado"
    assert oi["reviewed_by"] == "aprobado en Fase 4 (OI-01 a OI-08)"

    # Igual rigor que install_from_catalog: verificar contra git log real
    proc_toy_hash = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "plugins/toy/"],
        capture_output=True,
        text=True,
        check=True,
    )
    proc_toy_date = subprocess.run(
        ["git", "log", "-1", "--format=%aI", "--", "plugins/toy/"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert toy["active_commit_hash"] == proc_toy_hash.stdout.strip().lower()
    assert toy["reviewed_at"] == proc_toy_date.stdout.strip()
    assert toy["promoted_at"] == proc_toy_date.stdout.strip()

    proc_oi_hash = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "plugins/open_interpreter/"],
        capture_output=True,
        text=True,
        check=True,
    )
    proc_oi_date = subprocess.run(
        ["git", "log", "-1", "--format=%aI", "--", "plugins/open_interpreter/"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert oi["active_commit_hash"] == proc_oi_hash.stdout.strip().lower()
    assert oi["reviewed_at"] == proc_oi_date.stdout.strip()
    assert oi["promoted_at"] == proc_oi_date.stdout.strip()

    assert reg.is_curated("toy", toy["active_commit_hash"]) is True
    assert reg.is_curated("open_interpreter", oi["active_commit_hash"]) is True

