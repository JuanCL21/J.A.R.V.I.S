"""
JARVIS Core Lite (Fase 3).
Punto de arranque de la versión core-lite.
Regla de arquitectura: versions/* nunca contiene lógica de negocio propia —
solo define el perfil de permisos ('core-lite') y arranca el núcleo.
Sin servidor HTTP ni GUI escuchando.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Asegurar acceso a core cuando se ejecuta directamente
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.audit_log import AuditLogger, default_audit_logger
from core.dispatcher import Dispatcher
from core.logging_setup import get_logger, setup_logging
from core.plugin_loader import PluginLoader

CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_PROFILE = "core_lite"

logger = get_logger("core_lite")


def load_config(config_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Carga la configuración de core-lite desde archivo o valores por defecto."""
    path = Path(config_path) if config_path else CONFIG_FILE
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "version": "core-lite",
        "profile": DEFAULT_PROFILE,
        "plugins_dir": "plugins",
    }


def start_core_lite(
    config_path: Optional[Path | str] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> Tuple[Dispatcher, PluginLoader, AuditLogger]:
    """
    Inicializa el núcleo con el perfil 'core-lite' y carga los plugins autorizados.
    Retorna la tupla (dispatcher, plugin_loader, audit_logger).
    """
    config = load_config(config_path)
    profile = config.get("profile", DEFAULT_PROFILE)

    # 1. Configurar logging estructurado
    setup_logging()
    logger.info("Iniciando JARVIS Core Lite [perfil: %s]...", profile)

    # 2. Inicializar componentes del núcleo
    active_audit_logger = audit_logger or default_audit_logger
    loader = PluginLoader(audit_logger=active_audit_logger)
    dispatcher = Dispatcher(
        plugin_loader=loader,
        version_profile=profile,
        audit_logger=active_audit_logger,
    )

    # 3. Descubrir y cargar plugins autorizados en plugins_dir
    plugins_base = Path(__file__).parent.parent.parent / config.get("plugins_dir", "plugins")
    if plugins_base.is_dir():
        for plugin_dir in plugins_base.iterdir():
            if plugin_dir.is_dir() and (plugin_dir / "manifest.json").exists():
                loaded = loader.load(plugin_dir, version_profile=profile)
                if loaded:
                    logger.info("Plugin '%s' cargado exitosamente.", plugin_dir.name)
                else:
                    logger.warning(
                        "Plugin '%s' rechazado: no cumple con las capacidades de '%s'.",
                        plugin_dir.name,
                        profile,
                    )

    logger.info("JARVIS Core Lite inicializado listo para invocar acciones.")
    return dispatcher, loader, active_audit_logger


def main() -> None:
    """Función principal de arranque para ejecución directa."""
    dispatcher, loader, _ = start_core_lite()
    print(f"JARVIS Core Lite iniciado con éxito. Plugins cargados: {list(loader.loaded_plugins.keys())}")


if __name__ == "__main__":
    main()
