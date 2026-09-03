"""
Modelo de datos y registro de plugins en base de datos SQLite (database/jarvis.db).
Subfase A:
- Tabla plugin_registry con control de active_commit_hash y candidate_commit_hash.
- La unidad de confianza es el PAR (plugin_id, commit_hash) — nunca solo plugin_id.
- Separación estricta entre active_commit_hash (en ejecución) y candidate_commit_hash (detectado).
- register_plugin inserta SIEMPRE en status='no_verificado'. El ÚNICO camino a 'curado' es promote_to_curated().
- Resolución canónica de la ruta de la base de datos contra _REPO_ROOT, NUNCA contra os.getcwd().
- Sin efectos secundarios en import (inicialización perezosa de la base de datos).
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

VALID_STATUSES = ("no_verificado", "curado")

# Raíz canónica del repositorio calculada a partir de __file__, NUNCA de os.getcwd()
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "database" / "jarvis.db"

# TODO (PENDIENTE 1): Control de acceso real (rol/cuenta) para "aplicar actualización" y "promover".
# Se define junto con el auth general del dashboard en Fase 5, no antes.

# TODO (PENDIENTE 2): Estado de revocación/bloqueo para un plugin YA curado que después se descubre problemático (todavía no decidido).

# TODO (PENDIENTE 3): Qué gatilla que una cuenta vea el modo Avanzado, más allá de "oculto por defecto".


def resolve_db_path(db_path: Optional[str | Path] = None) -> Path:
    """
    Resuelve la ruta canónica del archivo de base de datos según la prioridad:
    1. Anulación programática explícita (parámetro db_path).
    2. Variable de entorno JARVIS_DB_PATH si está definida.
    3. Raíz fija del repositorio (_REPO_ROOT calculada desde __file__).
    NUNCA depende de os.getcwd().
    """
    if db_path is not None:
        return Path(db_path).resolve()

    env_path = os.environ.get("JARVIS_DB_PATH")
    if env_path:
        return Path(env_path).resolve()

    return _DEFAULT_DB_PATH.resolve()


class PluginRegistry:
    def __init__(self, db_path: Optional[str | Path] = None):
        """
        Inicializa el registro de plugins.
        La ruta de la base de datos se resuelve de forma determinista contra _REPO_ROOT.
        No ejecuta DDL ni crea archivos en disco durante la instanciación (lazy initialization).
        """
        self.db_path = resolve_db_path(db_path)
        self._db_initialized: bool = False

    def _ensure_db(self) -> None:
        """Crea la tabla plugin_registry en la base de datos SQLite si aún no existe."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS plugin_registry (
                        plugin_id TEXT PRIMARY KEY,
                        active_commit_hash TEXT NOT NULL,
                        candidate_commit_hash TEXT,
                        status TEXT NOT NULL CHECK (status IN ('no_verificado', 'curado')),
                        source_url TEXT NOT NULL,
                        reviewed_by TEXT,
                        reviewed_at TEXT,
                        promoted_at TEXT
                    )
                    """
                )
            self._db_initialized = True
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión a la base de datos garantizando que el esquema existe."""
        if not self._db_initialized:
            self._ensure_db()
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def register_plugin(
        self,
        plugin_id: str,
        active_commit_hash: str,
        source_url: str,
    ) -> None:
        """
        Registra un plugin en el registro.
        REGLA DE SEGURIDAD ESTRICTA: Todo plugin se registra obligatoriamente con status='no_verificado'
        y sin metadatos de auditoría (NULL). No existe ningún parámetro ni flag para alterar este estado.
        La promoción a 'curado' solo puede ocurrir a través de promote_to_curated().
        """
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO plugin_registry (
                        plugin_id, active_commit_hash, candidate_commit_hash,
                        status, source_url, reviewed_by, reviewed_at, promoted_at
                    ) VALUES (?, ?, NULL, 'no_verificado', ?, NULL, NULL, NULL)
                    ON CONFLICT(plugin_id) DO UPDATE SET
                        active_commit_hash = excluded.active_commit_hash,
                        candidate_commit_hash = NULL,
                        status = 'no_verificado',
                        source_url = excluded.source_url,
                        reviewed_by = NULL,
                        reviewed_at = NULL,
                        promoted_at = NULL
                    """,
                    (
                        plugin_id,
                        active_commit_hash,
                        source_url,
                    ),
                )
        finally:
            conn.close()

    def get_plugin(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene la información de registro de un plugin por su plugin_id."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM plugin_registry WHERE plugin_id = ?",
                (plugin_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_plugins(self) -> List[Dict[str, Any]]:
        """Lista todos los plugins registrados en el sistema."""
        conn = self._get_connection()
        try:
            rows = conn.execute("SELECT * FROM plugin_registry ORDER BY plugin_id ASC").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def set_candidate_commit(self, plugin_id: str, candidate_commit_hash: str) -> bool:
        """
        Registra un commit detectado en el repositorio remoto como candidato.
        REGLA CRÍTICA: Ninguna detección automática toca active_commit_hash ni status.
        active_commit_hash (lo que corre) queda intacto.
        """
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE plugin_registry
                    SET candidate_commit_hash = ?
                    WHERE plugin_id = ?
                    """,
                    (candidate_commit_hash, plugin_id),
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    def apply_candidate_update(self, plugin_id: str) -> bool:
        """
        Aplica la actualización candidata moviendo candidate_commit_hash -> active_commit_hash.
        REGLA CRÍTICA: Resetea SIEMPRE el status a 'no_verificado' (un commit nuevo nunca hereda
        el status del commit anterior) y limpia candidate_commit_hash, reviewed_by, reviewed_at y promoted_at.
        """
        # TODO (PENDIENTE 1): Control de acceso real (rol/cuenta) para "aplicar actualización".
        # TODO (PENDIENTE 2): Estado de revocación/bloqueo para un plugin YA curado.
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE plugin_registry
                    SET active_commit_hash = candidate_commit_hash,
                        candidate_commit_hash = NULL,
                        status = 'no_verificado',
                        reviewed_by = NULL,
                        reviewed_at = NULL,
                        promoted_at = NULL
                    WHERE plugin_id = ? AND candidate_commit_hash IS NOT NULL
                    """,
                    (plugin_id,),
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    def promote_to_curated(
        self,
        plugin_id: str,
        reviewed_by: str,
        reviewed_at: Optional[str] = None,
        promoted_at: Optional[str] = None,
    ) -> bool:
        """
        Promueve el active_commit_hash actual del plugin a status 'curado' tras revisión humana.
        REGLA CRÍTICA: Único método del sistema autorizado para establecer status='curado' y
        asignar reviewed_by, reviewed_at y promoted_at. No existe ninguna ruta automática alternativa.
        """
        # TODO (PENDIENTE 1): Control de acceso real (rol/cuenta) para "promover".
        now_ts = datetime.now(timezone.utc).isoformat()
        rev_at = reviewed_at or now_ts
        prom_at = promoted_at or now_ts

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE plugin_registry
                    SET status = 'curado',
                        reviewed_by = ?,
                        reviewed_at = ?,
                        promoted_at = ?
                    WHERE plugin_id = ?
                    """,
                    (reviewed_by, rev_at, prom_at, plugin_id),
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    def is_curated(self, plugin_id: str, commit_hash: Optional[str] = None) -> bool:
        """
        Verifica si el plugin (y opcionalmente su commit_hash específico) cuenta con status 'curado'.
        La unidad de confianza es el PAR (plugin_id, commit_hash).
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return False

        if plugin["status"] != "curado":
            return False

        if commit_hash is not None and plugin["active_commit_hash"] != commit_hash:
            return False

        return True


# TODO: default_plugin_registry a nivel de módulo eliminado para evitar efectos secundarios en imports.
# Instanciar PluginRegistry(db_path=...) explícitamente donde se requiera.
