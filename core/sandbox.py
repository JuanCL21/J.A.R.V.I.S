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
from typing import Dict, Iterable, List, Optional, Set

# Componentes de ruta exactos (directorios/subdirectorios) protegidos estructuralmente
# La coincidencia se realiza por COMPONENTES EXACTOS de ruta (Path.parts), evitando falsos positivos
# por substrings en nombres legítimos como 'digital_art/' o 'mi_credentials_guide/'.
_SENSITIVE_DIR_COMPONENTS: Set[str] = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".docker",
    ".kube",
    ".password-store",
    ".mozilla",
    ".git",
    "credentials",
}

# Subdirectorios compuestos protegidos estructuralmente (secuencia ordenada de componentes)
_SENSITIVE_COMPOUND_DIRS: List[List[str]] = [
    [".config", "google-chrome"],
    [".config", "chromium"],
    [".config", "BraveSoftware"],
    [".config", "microsoft-edge"],
]

# Patrones sensibles en nombres de archivo (protección estricta de credenciales y secretos)
# Se mantienen por substring en el nombre de archivo (filename) para evitar la vulnerabilidad
# original de JARVIS_Custom (donde variantes como 'credentials_prod.json' o 'my_credentials.txt'
# no eran bloqueadas si solo se comparaba por nombre exacto).
_SENSITIVE_FILE_PATTERNS: Set[str] = {
    ".env",
    "credentials",
    "id_rsa",
    "id_ed25519",
}

# Compatibilidad con módulos que importen _SENSITIVE_SUBDIRS históricamente
_SENSITIVE_SUBDIRS: Set[str] = _SENSITIVE_DIR_COMPONENTS | _SENSITIVE_FILE_PATTERNS


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
    allow_directory: bool = False,
    is_directory: Optional[bool] = None,
) -> bool:
    """
    Verifica que la ruta objetivo:
    1. Se encuentre estrictamente confinada dentro de sandbox_root (sin escapar vía '..').
    2. No acceda a ningún directorio sensible en _SENSITIVE_DIR_COMPONENTS
       (coincidencia por COMPONENTES EXACTOS de ruta en Path.parts, evitando falsos positivos
       por substring libre en nombres legítimos como 'digital_art/' o 'mi_credentials_guide/').
    3. Para directorios (modo allow_directory=True o is_directory=True):
       - Permite sufijo vacío sin forzar extensiones de archivo.
    4. Para archivos (modo allow_directory=False):
       - No contenga patrones de secretos en el nombre de archivo (_SENSITIVE_FILE_PATTERNS:
         .env, credentials, id_rsa, etc., por substring para evitar la vulnerabilidad histórica).
       - Cumpla con una lista de extensiones permitidas (DEFAULT_ALLOWED_EXTENSIONS si None).
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
            resolved_target.relative_to(root)
        except ValueError:
            # Está fuera del sandbox root
            return False

        # 2. Comprobación contra componentes exactos de ruta sensibles (Path.parts)
        # Evita falsos positivos por substrings en directorios como 'digital_art' o 'mi_credentials_guide'
        target_parts_lower = [p.lower() for p in resolved_target.parts]
        for sensitive_dir in _SENSITIVE_DIR_COMPONENTS:
            if sensitive_dir.lower() in target_parts_lower:
                return False

        # Comprobación de subdirectorios compuestos (ej. .config/google-chrome)
        for compound in _SENSITIVE_COMPOUND_DIRS:
            c_len = len(compound)
            compound_lower = [c.lower() for c in compound]
            for i in range(len(target_parts_lower) - c_len + 1):
                if target_parts_lower[i : i + c_len] == compound_lower:
                    return False

        # 3. Validación según modo: directorio vs archivo
        is_dir_mode = bool(allow_directory or (is_directory is True))
        if is_dir_mode:
            # En modo directorio se permite sufijo vacío y no se exige extensión de archivo
            return True

        # 4. Modo archivo: comprobación de patrones sensibles en el nombre de archivo (filename)
        filename_lower = resolved_target.name.lower()
        for sensitive_pattern in _SENSITIVE_FILE_PATTERNS:
            if sensitive_pattern.lower() in filename_lower:
                return False

        # 5. Allowlist de extensiones para archivos (por defecto DEFAULT_ALLOWED_EXTENSIONS si None)
        effective_allowed = (
            allowed_extensions if allowed_extensions is not None else DEFAULT_ALLOWED_EXTENSIONS
        )
        normalized_allowed = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in effective_allowed
        }
        if resolved_target.suffix.lower() not in normalized_allowed:
            return False

        return True

    except Exception:
        return False
