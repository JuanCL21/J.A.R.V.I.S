"""
Plugin de juguete (Fase 2).
Implementa la acción 'get_time' para devolver la hora del sistema.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def get_time(format_str: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve la fecha y hora actual del sistema en UTC."""
    now = datetime.now(timezone.utc)
    if format_str:
        formatted = now.strftime(format_str)
    else:
        formatted = now.isoformat()

    return {
        "iso": now.isoformat(),
        "timestamp": now.timestamp(),
        "formatted": formatted,
    }


class Plugin:
    """Clase del plugin Toy."""

    def get_time(self, format_str: Optional[str] = None) -> Dict[str, Any]:
        return get_time(format_str=format_str)
