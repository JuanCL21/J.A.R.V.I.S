"""
Pruebas de la Subfase A: Modelo de datos plugin_registry.
Cubre:
1. Creación y estructura de la tabla plugin_registry en SQLite.
2. Separación estricta entre active_commit_hash y candidate_commit_hash.
3. Test requerido: crear plugin con commit A curado, simular detección de commit B,
   verificar que active_commit_hash sigue en A y B queda solo en candidate_commit_hash.
4. Unidad de confianza como par (plugin_id, commit_hash) — un commit nuevo no hereda status curado.
"""

from pathlib import Path
import sqlite3
import pytest

from core.plugin_registry import PluginRegistry


@pytest.fixture
def registry(tmp_path: Path) -> PluginRegistry:
    """Instancia de PluginRegistry sobre base de datos aislada en tmp_path."""
    db_path = tmp_path / "test_jarvis.db"
    return PluginRegistry(db_path=db_path)


def test_subfase_a_plugin_registry_table_structure(registry: PluginRegistry):
    """Verifica que la tabla plugin_registry contenga las columnas y restricciones requeridas."""
    conn = registry._get_connection()
    try:
        # Obtener información de columnas
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

    # 1. Crear plugin con commit A curado
    registry.register_plugin(
        plugin_id=plugin_id,
        active_commit_hash=commit_a,
        source_url=source_url,
        status="curado",
        reviewed_by="auditor_principal",
        reviewed_at="2026-09-02T22:00:00Z",
        promoted_at="2026-09-02T22:05:00Z",
    )

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
        status="curado",
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
