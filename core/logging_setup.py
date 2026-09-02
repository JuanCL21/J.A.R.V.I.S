"""
Configuración centralizada de logging estructurado para JARVIS.
Permite salida por consola y rotación de archivos en logs/.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


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

    # Handler de archivo con rotación
    if log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=log_path / log_file_name,
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
