"""
Cargador y validador de manifiestos de plugins para JARVIS.
Revisión de auditor:
- schema_version obligatorio desde la versión 1.
- Validación estricta de capacidades contra capability_catalog (ValueError si está fuera del catálogo).
- Namespacing de acciones: plugin_id.action para evitar colisiones estructuralmente.
- Comprobación contra perfiles de versión.
"""

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .audit_log import AuditLogger, default_audit_logger
from .capability_catalog import is_valid_capability, validate_capabilities
from .version_profiles import get_profile_capabilities, is_capability_allowed

SUPPORTED_SCHEMA_VERSIONS = {"1"}


@dataclass
class ActionDefinition:
    name: str
    capability: str
    description: str = ""
    handler: Optional[Callable[..., Any]] = None


@dataclass
class PluginManifest:
    schema_version: str
    id: str
    name: str
    version: str
    capabilities: List[str] = field(default_factory=list)
    actions: List[ActionDefinition] = field(default_factory=list)


class PluginLoader:
    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self.loaded_plugins: Dict[str, PluginManifest] = {}
        # Mapeo de "plugin_id.action_name" -> ActionDefinition
        self.registered_actions: Dict[str, ActionDefinition] = {}
        self.audit_logger = audit_logger or default_audit_logger

    def parse_manifest_dict(self, data: Dict[str, Any]) -> PluginManifest:
        """
        Valida y parsea un diccionario de manifiesto.
        Lanza ValueError si falta schema_version, si es inválido, o si contiene capacidades fuera de catálogo.
        """
        if "schema_version" not in data or not str(data["schema_version"]).strip():
            raise ValueError(
                "Manifiesto inválido: Falta el campo obligatorio 'schema_version' (Revisión de auditor #1)."
            )

        schema_version = str(data["schema_version"])
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Versión de schema '{schema_version}' no soportada. Soportadas: {SUPPORTED_SCHEMA_VERSIONS}"
            )

        plugin_id = data.get("id")
        if not plugin_id or not isinstance(plugin_id, str):
            raise ValueError("Manifiesto inválido: 'id' es requerido y debe ser un string no vacío.")

        name = data.get("name", plugin_id)
        version = data.get("version", "1.0.0")
        capabilities = data.get("capabilities", [])

        # Validar capacidades contra el catálogo cerrado (NUC-01)
        validate_capabilities(capabilities)

        actions_data = data.get("actions", [])
        actions: List[ActionDefinition] = []

        for act in actions_data:
            act_name = act.get("name")
            act_cap = act.get("capability")
            act_desc = act.get("description", "")

            if not act_name or not act_cap:
                raise ValueError("Cada acción debe declarar 'name' y 'capability'.")

            # Validar que la capacidad de la acción pertenezca al catálogo
            validate_capabilities([act_cap])

            # La capacidad debe estar declarada en las capacidades del plugin
            if act_cap not in capabilities:
                raise ValueError(
                    f"La acción '{act_name}' requiere la capacidad '{act_cap}', pero no está declarada en 'capabilities' del plugin."
                )

            actions.append(
                ActionDefinition(
                    name=act_name,
                    capability=act_cap,
                    description=act_desc,
                )
            )

        return PluginManifest(
            schema_version=schema_version,
            id=plugin_id,
            name=name,
            version=version,
            capabilities=capabilities,
            actions=actions,
        )

    def load_manifest_file(self, manifest_path: Path | str) -> PluginManifest:
        """Carga y valida un archivo manifest.json."""
        path = Path(manifest_path)
        if not path.is_file():
            raise FileNotFoundError(f"Archivo de manifiesto no encontrado: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self.parse_manifest_dict(data)

    def register_plugin_actions(
        self,
        manifest: PluginManifest,
        handlers: Optional[Dict[str, Callable[..., Any]]] = None,
        module: Optional[Any] = None,
    ) -> None:
        """
        Registra las acciones de un plugin usando el namespace 'plugin_id.action_name'.
        Evita estructuralmente cualquier colisión de nombres entre plugins (NUC-06).
        """
        self.loaded_plugins[manifest.id] = manifest

        for action in manifest.actions:
            handler = None
            if handlers and action.name in handlers:
                handler = handlers[action.name]
            elif module is not None:
                # Buscar función o método en el módulo
                if hasattr(module, action.name):
                    handler = getattr(module, action.name)
                elif hasattr(module, "Plugin") and hasattr(getattr(module, "Plugin"), action.name):
                    plugin_cls = getattr(module, "Plugin")
                    instance = plugin_cls() if isinstance(plugin_cls, type) else plugin_cls
                    handler = getattr(instance, action.name)

            action_def = ActionDefinition(
                name=action.name,
                capability=action.capability,
                description=action.description,
                handler=handler,
            )

            # Registro con namespace obligatorio: plugin_id.action_name
            full_action_key = f"{manifest.id}.{action.name}"
            self.registered_actions[full_action_key] = action_def

    def load_from_directory(
        self,
        plugin_dir: Path | str,
        version_profile: Optional[str] = None,
    ) -> bool:
        """
        Carga un plugin desde su directorio (debe contener manifest.json y opcionalmente plugin.py).
        Si se especifica version_profile, valida si el perfil autoriza todas las capacidades del plugin.
        Si no las autoriza, no carga el plugin y devuelve False.
        """
        dir_path = Path(plugin_dir)
        manifest_file = dir_path / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"No se encontró manifest.json en {dir_path}")

        manifest = self.load_manifest_file(manifest_file)

        # Comprobar si el perfil de versión permite este plugin
        if version_profile:
            allowed_caps = get_profile_capabilities(version_profile)
            plugin_caps = set(manifest.capabilities)
            if not plugin_caps.issubset(allowed_caps):
                denied_caps = list(plugin_caps - allowed_caps)
                self.audit_logger.log_invocation(
                    plugin_id=manifest.id,
                    action="load_plugin",
                    capability=",".join(sorted(denied_caps)),
                    allowed=False,
                    result_status="denied",
                    reason="capability_denied",
                    details={
                        "profile": version_profile,
                        "plugin_capabilities": manifest.capabilities,
                        "denied_capabilities": denied_caps,
                    },
                )
                return False

        # Cargar plugin.py si existe
        plugin_py = dir_path / "plugin.py"
        module = None
        if plugin_py.exists():
            spec = importlib.util.spec_from_file_location(f"plugin_{manifest.id}", plugin_py)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

        self.register_plugin_actions(manifest, module=module)
        return True

    def load(
        self,
        plugin_dir: Path | str,
        version_profile: Optional[str] = None,
    ) -> bool:
        """Alias para load_from_directory."""
        return self.load_from_directory(plugin_dir, version_profile=version_profile)

    def register_programmatic_plugin(
        self,
        manifest_data: Dict[str, Any],
        handlers: Dict[str, Callable[..., Any]],
        version_profile: Optional[str] = None,
    ) -> bool:
        """
        Registra un plugin directamente a partir de un dict y handlers (útil para tests y plugins en memoria).
        """
        manifest = self.parse_manifest_dict(manifest_data)

        if version_profile:
            allowed_caps = get_profile_capabilities(version_profile)
            plugin_caps = set(manifest.capabilities)
            if not plugin_caps.issubset(allowed_caps):
                denied_caps = list(plugin_caps - allowed_caps)
                self.audit_logger.log_invocation(
                    plugin_id=manifest.id,
                    action="load_plugin",
                    capability=",".join(sorted(denied_caps)),
                    allowed=False,
                    result_status="denied",
                    reason="capability_denied",
                    details={
                        "profile": version_profile,
                        "plugin_capabilities": manifest.capabilities,
                        "denied_capabilities": denied_caps,
                    },
                )
                return False

        self.register_plugin_actions(manifest, handlers=handlers)
        return True
