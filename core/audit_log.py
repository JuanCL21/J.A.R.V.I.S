"""
Registro de auditoría persistente en SQLite (database/jarvis.db).
Revisión de auditor: Cada invoke() — permitido o denegado — se escribe a SQLite,
garantizando trazabilidad inmutable y consultable.
Manejo explícito de conexiones con cierre garantizado (try/finally).
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuditLogger:
    def __init__(self, db_path: str | Path = "database/jarvis.db"):
        self.db_path = Path(db_path)
        self._ensure_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
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
        finally:
            conn.close()

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
    ) -> List[Dict[str, Any]]:
        """Consulta los registros de auditoría más recientes con cierre garantizado de conexión."""
        query = "SELECT * FROM audit_logs"
        params: list[Any] = []
        if plugin_id:
            query += " WHERE plugin_id = ?"
            params.append(plugin_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        conn = self._get_connection()
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


# Instancia por defecto para el núcleo
default_audit_logger = AuditLogger()
