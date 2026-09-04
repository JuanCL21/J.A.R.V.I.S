"""
Configuración centralizada de logging estructurado para JARVIS.
Permite salida por consola y rotación de archivos en logs/.
Resolución canónica de directorio de logs contra _REPO_ROOT, nunca contra os.getcwd().
"""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from typing import Optional

# Raíz canónica del repositorio calculada a partir de __file__, NUNCA de os.getcwd()
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG_DIR = _REPO_ROOT / "logs"

DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def resolve_log_dir(log_dir: Optional[str | Path] = "logs") -> Optional[Path]:
    """
    Resuelve la ruta canónica del directorio de logs contra _REPO_ROOT, nunca contra os.getcwd().
    Prioridad:
    1. Si log_dir es None, retorna None (deshabilita logging en archivo).
    2. Si log_dir es un Path o str explícito distinto de 'logs':
       se resuelve contra _REPO_ROOT si es relativo, o directo si es absoluto.
    3. Variable de entorno JARVIS_LOG_DIR si está definida.
    4. Directorio canónico (_REPO_ROOT / 'logs').
    """
    if log_dir is None:
        return None

    if log_dir != "logs":
        p = Path(log_dir)
        return p.resolve() if p.is_absolute() else (_REPO_ROOT / p).resolve()

    env_dir = os.environ.get("JARVIS_LOG_DIR")
    if env_dir:
        p = Path(env_dir)
        return p.resolve() if p.is_absolute() else (_REPO_ROOT / p).resolve()

    return _DEFAULT_LOG_DIR.resolve()


def setup_logging(
    log_dir: Optional[str | Path] = "logs",
    log_file_name: str = "jarvis.log",
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 5,
) -> None:
    """Configura los handlers globales de logging con rotación."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Evitar duplicar handlers si ya se configuraron
    if root_logger.handlers:
        return

    formatter = logging.Formatter(fmt=DEFAULT_FORMAT, datefmt=DEFAULT_DATE_FORMAT)

    # Handler de consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # Handler de archivo con rotación resuelto contra _REPO_ROOT
    resolved_dir = resolve_log_dir(log_dir)
    if resolved_dir is not None:
        resolved_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=resolved_dir / log_file_name,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Obtiene un logger estructurado con el nombre dado."""
    return logging.getLogger(name)
