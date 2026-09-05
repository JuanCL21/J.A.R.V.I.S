"""
Registro de auditoría persistente en SQLite (database/jarvis.db).
Revisión de auditor: Cada invoke() — permitido o denegado — se escribe a SQLite,
garantizando trazabilidad inmutable y consultable.
Manejo explícito de conexiones con cierre garantizado (try/finally).
Resolución canónica de ruta contra _REPO_ROOT e inicialización perezosa (lazy).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from .plugin_registry import resolve_db_path, _REPO_ROOT


class AuditLogger:
    def __init__(self, db_path: Optional[str | Path] = None):
        """
        Inicializa el registrador de auditoría.
        La ruta de la base de datos se resuelve contra _REPO_ROOT, nunca contra os.getcwd().
        Inicialización perezosa: no crea archivos ni ejecuta CREATE TABLE hasta la primera operación.
        """
        self.db_path = resolve_db_path(db_path)
        self._db_initialized: bool = False

    def _ensure_db(self) -> None:
        """Crea la tabla audit_logs si no existe."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        plugin_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        capability TEXT,
                        allowed INTEGER NOT NULL,
                        result_status TEXT NOT NULL,
                        reason TEXT,
                        details TEXT
                    )
                    """
                )
            self._db_initialized = True
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión a la base de datos asegurando inicialización previa."""
        if not self._db_initialized:
            self._ensure_db()
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def log_invocation(
        self,
        plugin_id: str,
        action: str,
        capability: Optional[str],
        allowed: bool,
        result_status: str,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any] | str] = None,
    ) -> int:
        """Registra un intento de invocación de acción en la base de datos con cierre garantizado de conexión."""
        # TODO (DECISIÓN DE PRODUCTO PENDIENTE): audit_log guarda los parámetros completos de cada
        # acción (details={"params": params}) sin enmascarar valores sensibles (tokens, contraseñas,
        # api keys) que un plugin reciba como argumento. Se requiere definir a nivel de producto qué
        # campos o patrones se consideran sensibles para aplicar redactado/enmascarado antes de persistir.
        ts = datetime.now(timezone.utc).isoformat()
        details_str = (
            json.dumps(details, ensure_ascii=False)
            if isinstance(details, dict)
            else (str(details) if details is not None else None)
        )

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO audit_logs (
                        timestamp, plugin_id, action, capability, allowed, result_status, reason, details
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts,
                        plugin_id,
                        action,
                        capability,
                        1 if allowed else 0,
                        result_status,
                        reason,
                        details_str,
                    ),
                )
                return cursor.lastrowid or 0
        finally:
            conn.close()

    def query_logs(
        self,
        plugin_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Consulta los registros de auditoría más recientes con cierre garantizado de conexión."""
        query = "SELECT * FROM audit_logs"
        params: list[Any] = []
        if plugin_id:
            query += " WHERE plugin_id = ?"
            params.append(plugin_id)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._get_connection()
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


# TODO: default_audit_logger a nivel de módulo eliminado para evitar instanciación con efectos secundarios en imports.
# Reemplazar su import y uso por instanciación explícita de AuditLogger(...) en:
# - core/dispatcher.py (Dispatcher.__init__)
# - core/plugin_loader.py (PluginLoader.__init__)
# - core/__init__.py
# - versions/core_lite/main.py

_default_audit_logger: Optional[AuditLogger] = None


def get_default_audit_logger() -> AuditLogger:
    """Retorna una instancia singleton perezosa de AuditLogger."""
    global _default_audit_logger
    if _default_audit_logger is None:
        _default_audit_logger = AuditLogger()
    return _default_audit_logger


def __getattr__(name: str) -> Any:
    """Acceso perezoso compatible hacia atrás para default_audit_logger."""
    if name == "default_audit_logger":
        return get_default_audit_logger()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
