"""
Gestión de sandboxing y validación estricta de rutas de archivos.
Revisión de auditor y seguridad:
- Raíz de sandbox configurable de forma explícita (variable de entorno JARVIS_SANDBOX_ROOT
  o inicialización explícita), NUNCA implícita del directorio de trabajo (os.getcwd()).
- Allowlist de extensiones seguras por defecto (DEFAULT_ALLOWED_EXTENSIONS) en is_safe_path()
  si el llamador no especifica una lista propia, previniendo comportamientos de blacklist pura.
- _SENSITIVE_SUBDIRS y patrones sensibles protegen estructuralmente credenciales (.env*, *credentials*),
  llaves SSH (.ssh, id_rsa*), configuraciones de nube (.aws, .kube) y perfiles de navegadores.
- sandbox_root ignora rutas libres pasadas por plugins (ej. /etc) y resuelve únicamente contra raíces fijas autorizadas.
"""

import os
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

# Subdirectorios, archivos y patrones sensibles protegidos estructuralmente por prefijo/substring
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
    "credentials",
    "id_rsa",
    "id_ed25519",
}

# Allowlist de extensiones seguras por defecto (Opción B: protege contra archivos ejecutables/secretos)
DEFAULT_ALLOWED_EXTENSIONS: Set[str] = {
    ".txt",
    ".md",
    ".py",
    ".pptx",
    ".csv",
    ".log",
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
}

# Raíz canónica del repositorio calculada a partir de __file__, NUNCA de os.getcwd()
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Variable global para anular programáticamente la raíz por defecto
_CUSTOM_DEFAULT_SANDBOX_ROOT: Optional[Path] = None


def get_default_sandbox_base() -> Path:
    """
    Obtiene la raíz de sandbox por defecto del sistema según la siguiente prioridad:
    1. Anulación programática explícita (set_default_sandbox_root).
    2. Variable de entorno JARVIS_SANDBOX_ROOT.
    3. Raíz fija del proyecto (_REPO_ROOT calculada desde __file__).
    NUNCA depende de os.getcwd().
    """
    if _CUSTOM_DEFAULT_SANDBOX_ROOT is not None:
        return _CUSTOM_DEFAULT_SANDBOX_ROOT.resolve()

    env_root = os.environ.get("JARVIS_SANDBOX_ROOT")
    if env_root:
        return Path(env_root).resolve()

    return _REPO_ROOT.resolve()


def set_default_sandbox_root(path: Optional[Path | str]) -> None:
    """Configura explícitamente la raíz por defecto del sandbox."""
    global _CUSTOM_DEFAULT_SANDBOX_ROOT
    if path is None:
        _CUSTOM_DEFAULT_SANDBOX_ROOT = None
    else:
        _CUSTOM_DEFAULT_SANDBOX_ROOT = Path(path).resolve()
    reset_authorized_roots()


# Registro de raíces de sandbox autorizadas (valores fijos permitidos)
_AUTHORIZED_ROOTS: Dict[str, Path] = {}


def reset_authorized_roots(base_path: Optional[Path | str] = None) -> None:
    """Restablece el registro de raíces autorizadas a sus valores predeterminados."""
    base = Path(base_path).resolve() if base_path else get_default_sandbox_base()
    _AUTHORIZED_ROOTS.clear()
    _AUTHORIZED_ROOTS["default"] = base
    _AUTHORIZED_ROOTS["workspace"] = base
    _AUTHORIZED_ROOTS["temp"] = base / "temp"


# Inicialización de raíces autorizadas
reset_authorized_roots()


def register_authorized_root(alias: str, path: Path | str) -> None:
    """Registra una raíz fija autorizada (para pruebas o configuración inicial)."""
    _AUTHORIZED_ROOTS[alias] = Path(path).resolve()


def resolve_sandbox_root(requested_root: Optional[str | Path] = None) -> Path:
    """
    Resuelve la raíz del sandbox.
    Si el invocador pasa un alias autorizado (ej. 'workspace', 'temp'), se utiliza esa ruta fija.
    Si pasa una ruta libre/arbitraria no autorizada (ej. '/etc', '/root'), se IGNORA y se
    retorna la raíz autorizada predeterminada ('default').
    """
    if not _AUTHORIZED_ROOTS:
        reset_authorized_roots()

    if requested_root is None:
        return _AUTHORIZED_ROOTS.get("default", get_default_sandbox_base())

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
    return _AUTHORIZED_ROOTS.get("default", get_default_sandbox_base())


def is_safe_path(
    target_path: str | Path,
    sandbox_root: Optional[str | Path] = None,
    allowed_extensions: Optional[Iterable[str]] = None,
) -> bool:
    """
    Verifica que la ruta objetivo:
    1. Se encuentre estrictamente confinada dentro de sandbox_root (sin escapar vía '..').
    2. No acceda a ningún directorio o archivo en _SENSITIVE_SUBDIRS
       (coincidencia por partes, prefijo y substring: .env*, *credentials*, id_rsa*, etc.).
    3. Cumpla con una lista de extensiones permitidas:
       - Si allowed_extensions se especifica, se valida contra dicha lista.
       - Si allowed_extensions es None, se aplica la allowlist por defecto DEFAULT_ALLOWED_EXTENSIONS
         (Decisión de diseño: Opción B, garantizando que nunca opere como blacklist pura).
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

        # 2. Comprobación contra subdirectorios/archivos sensibles por substring y prefijo
        target_str = str(resolved_target)
        target_parts = set(resolved_target.parts)
        filename_lower = resolved_target.name.lower()

        for sensitive in _SENSITIVE_SUBDIRS:
            sensitive_lower = sensitive.lower()
            if "/" in sensitive_lower:
                # Caso de subdirectorios compuestos como .config/google-chrome
                if sensitive_lower in target_str.lower():
                    return False
            else:
                # Comprobar si el nombre del archivo o alguna parte contiene el patrón sensible
                if sensitive_lower in filename_lower:
                    return False
                if any(sensitive_lower in part.lower() for part in target_parts):
                    return False

        # 3. Allowlist de extensiones (por defecto DEFAULT_ALLOWED_EXTENSIONS si None)
        effective_allowed = allowed_extensions if allowed_extensions is not None else DEFAULT_ALLOWED_EXTENSIONS
        normalized_allowed = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in effective_allowed
        }
        if resolved_target.suffix.lower() not in normalized_allowed:
            return False

        return True

    except Exception:
        return False
