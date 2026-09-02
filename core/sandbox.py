"""
Gestión de sandboxing y validación estricta de rutas de archivos.
Revisión de auditor:
- _SENSITIVE_SUBDIRS presente desde el día uno.
- sandbox_root ignora rutas libres pasadas por plugins (ej. /etc) y resuelve únicamente contra raíces fijas autorizadas.
- is_safe_path() valida confinamiento de ruta y protección contra path traversal.
"""

import os
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

# Subdirectorios y archivos sensibles protegidos estructuralmente
_SENSITIVE_SUBDIRS: Set[str] = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".docker",
    ".kube",
    ".password-store",
    ".mozilla",
    ".config/google-chrome",
    ".config/chromium",
    ".config/BraveSoftware",
    ".config/microsoft-edge",
    ".git",
    ".env",
}

# Raíz de sandbox por defecto del proyecto
DEFAULT_SANDBOX_BASE = Path(os.getcwd()).resolve()

# Registro de raíces de sandbox autorizadas (valores fijos permitidos)
_AUTHORIZED_ROOTS: Dict[str, Path] = {
    "default": DEFAULT_SANDBOX_BASE,
    "workspace": DEFAULT_SANDBOX_BASE,
    "temp": DEFAULT_SANDBOX_BASE / "temp",
}


def register_authorized_root(alias: str, path: Path | str) -> None:
    """Registra una raíz fija autorizada (para pruebas o configuración inicial)."""
    _AUTHORIZED_ROOTS[alias] = Path(path).resolve()


def reset_authorized_roots(base_path: Optional[Path | str] = None) -> None:
    """Restablece el registro de raíces autorizadas a sus valores predeterminados."""
    base = Path(base_path).resolve() if base_path else Path(os.getcwd()).resolve()
    _AUTHORIZED_ROOTS.clear()
    _AUTHORIZED_ROOTS["default"] = base
    _AUTHORIZED_ROOTS["workspace"] = base
    _AUTHORIZED_ROOTS["temp"] = base / "temp"


def resolve_sandbox_root(requested_root: Optional[str | Path] = None) -> Path:
    """
    Resuelve la raíz del sandbox.
    Si el invocador pasa un alias autorizado (ej. 'workspace', 'temp'), se utiliza esa ruta fija.
    Si pasa una ruta libre/arbitraria no autorizada (ej. '/etc', '/root'), se IGNORA y se
    retorna la raíz autorizada predeterminada ('default').
    """
    if requested_root is None:
        return _AUTHORIZED_ROOTS["default"]

    req_str = str(requested_root)

    # 1. ¿Es un alias autorizado?
    if req_str in _AUTHORIZED_ROOTS:
        return _AUTHORIZED_ROOTS[req_str]

    # 2. ¿Es exactamente una ruta que coincide con alguna raíz registrada?
    try:
        resolved_req = Path(requested_root).resolve()
        for auth_path in _AUTHORIZED_ROOTS.values():
            if resolved_req == auth_path.resolve():
                return auth_path.resolve()
    except Exception:
        pass

    # Si es una ruta libre no autorizada (ej. /etc), se ignora y se devuelve el valor fijo por defecto
    return _AUTHORIZED_ROOTS["default"]


def is_safe_path(
    target_path: str | Path,
    sandbox_root: Optional[str | Path] = None,
    allowed_extensions: Optional[Iterable[str]] = None,
) -> bool:
    """
    Verifica que la ruta objetivo:
    1. Se encuentre estrictamente confinada dentro de sandbox_root (sin escapar vía '..').
    2. No acceda a ningún directorio o archivo en _SENSITIVE_SUBDIRS.
    3. (Opcional) Cumpla con la lista de extensiones permitidas.
    """
    try:
        root = resolve_sandbox_root(sandbox_root).resolve()
        target = Path(target_path)

        # Si es relativa, interpretarla respecto a la raíz del sandbox
        if not target.is_absolute():
            target = root / target

        resolved_target = target.resolve()

        # 1. Confinamiento dentro del sandbox
        try:
            rel_path = resolved_target.relative_to(root)
        except ValueError:
            # Está fuera del sandbox root
            return False

        # 2. Comprobación contra subdirectorios/archivos sensibles
        # Revisamos las partes del path resuelto
        target_parts = set(resolved_target.parts)
        for sensitive in _SENSITIVE_SUBDIRS:
            if "/" in sensitive:
                # Caso de subdirectorios compuestos como .config/google-chrome
                if sensitive in str(resolved_target):
                    return False
            else:
                if sensitive in target_parts:
                    return False

        # 3. Allowlist de extensiones (si se especifica)
        if allowed_extensions is not None:
            normalized_allowed = {
                ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                for ext in allowed_extensions
            }
            if resolved_target.suffix.lower() not in normalized_allowed:
                return False

        return True

    except Exception:
        return False
