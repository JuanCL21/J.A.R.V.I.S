"""
JARVIS Core Package.
"""

from .capability_catalog import (
    CAPABILITY_CATALOG,
    VALID_CAPABILITIES,
    is_valid_capability,
    capability_requires_confirmation,
    validate_capabilities,
)
from .version_profiles import (
    VERSION_PROFILES,
    get_profile_capabilities,
    is_capability_allowed,
    register_profile,
)
from .audit_log import AuditLogger, default_audit_logger
from .sandbox import (
    _SENSITIVE_SUBDIRS,
    DEFAULT_ALLOWED_EXTENSIONS,
    get_default_sandbox_base,
    set_default_sandbox_root,
    resolve_sandbox_root,
    is_safe_path,
    register_authorized_root,
    reset_authorized_roots,
)
from .secrets import load_secrets, get_secret, set_secret
from .logging_setup import setup_logging, get_logger
from .plugin_loader import PluginLoader, PluginManifest, ActionDefinition
from .dispatcher import Dispatcher
from .plugin_registry import (
    PluginRegistry,
    resolve_db_path,
    FIRST_PARTY_PLUGINS,
    migrate_first_party_plugins,
)
from .plugin_installer import (
    PluginInstaller,
    install_from_catalog,
    install_from_url,
    resolve_catalog_path,
    load_curated_catalog,
)

# TODO: default_plugin_registry a nivel de módulo eliminado para evitar efectos secundarios en imports.
# Instanciar PluginRegistry explícitamente donde se requiera.

__all__ = [
    "CAPABILITY_CATALOG",
    "VALID_CAPABILITIES",
    "is_valid_capability",
    "capability_requires_confirmation",
    "validate_capabilities",
    "VERSION_PROFILES",
    "get_profile_capabilities",
    "is_capability_allowed",
    "AuditLogger",
    "default_audit_logger",
    "PluginRegistry",
    "resolve_db_path",
    "FIRST_PARTY_PLUGINS",
    "migrate_first_party_plugins",
    "PluginInstaller",
    "install_from_catalog",
    "install_from_url",
    "resolve_catalog_path",
    "load_curated_catalog",
    "_SENSITIVE_SUBDIRS",
    "resolve_sandbox_root",
    "is_safe_path",
    "register_authorized_root",
    "reset_authorized_roots",
    "load_secrets",
    "get_secret",
    "set_secret",
    "setup_logging",
    "get_logger",
    "PluginLoader",
    "PluginManifest",
    "ActionDefinition",
    "Dispatcher",
]
