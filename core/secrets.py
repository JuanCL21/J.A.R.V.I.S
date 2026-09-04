"""
Gestión segura de secretos en archivos .env (permisos 0600).
Nunca serializar secretos en JSON ni exponerlos en logs.
"""

import os
from pathlib import Path
from typing import Dict, Optional


def _enforce_secure_permissions(path: Path) -> None:
    """Aplica permisos 0600 (lectura/escritura exclusiva para el usuario) en sistemas POSIX."""
    if os.name != "nt" and path.exists():
        os.chmod(path, 0o600)


def load_secrets(env_path: str | Path = ".env") -> Dict[str, str]:
    """Carga variables desde un archivo .env."""
    path = Path(env_path)
    if not path.is_file():
        return {}

    _enforce_secure_permissions(path)

    secrets: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                secrets[key] = val
    return secrets


def get_secret(
    key: str,
    default: Optional[str] = None,
    env_path: str | Path = ".env",
) -> Optional[str]:
    """Obtiene el valor de un secreto desde el archivo .env o variables de entorno del sistema."""
    # Prioridad: variable de entorno de proceso > archivo .env > default
    if key in os.environ:
        return os.environ[key]

    secrets = load_secrets(env_path)
    return secrets.get(key, default)


def set_secret(
    key: str,
    value: str,
    env_path: str | Path = ".env",
) -> None:
    """Guarda o actualiza un secreto en el archivo .env con permisos 0600 atómicos desde la creación."""
    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    secrets = load_secrets(path)
    secrets[key] = value

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    # Creación atómica con modo 0o600 (sin ventana de lectura/exposición bajo umask por defecto)
    fd = os.open(path, flags, 0o600)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with open(fd, "w", encoding="utf-8", closefd=False) as f:
            for k, v in secrets.items():
                f.write(f"{k}={v}\n")
    finally:
        os.close(fd)

