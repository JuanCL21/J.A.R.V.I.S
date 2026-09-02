"""
Perfiles de versiones de JARVIS.
Define qué capacidades tiene autorizadas cada versión del sistema.
Regla: versions/* nunca contiene lógica de negocio propia — solo define el perfil y arranca el núcleo.
"""

from typing import Dict, FrozenSet, Set
from .capability_catalog import VALID_CAPABILITIES

# Perfiles base canónicos
_BASE_PROFILES: Dict[str, Set[str]] = {
    "core_lite": {
        "system_info",
        "filesystem_read",
    },
    "core_full": {
        "system_info",
        "filesystem_read",
        "filesystem_write",
        "code_execution",
        "network_access",
        "device_management",
        "audio_synthesis",
        "audio_capture",
    },
    "asistente": {
        "system_info",
        "filesystem_read",
        "network_access",
        "audio_synthesis",
        "audio_capture",
    },
    "local": {
        "system_info",
        "filesystem_read",
        "filesystem_write",
        "code_execution",
        "network_access",
        "audio_synthesis",
        "audio_capture",
    },
    "movil": {
        "system_info",
        "network_access",
        "audio_synthesis",
        "audio_capture",
    },
}

# Diccionario público inmutable con soporte para variantes con guion y guion bajo
VERSION_PROFILES: Dict[str, FrozenSet[str]] = {}
for name, caps in _BASE_PROFILES.items():
    # Validar que todas las capacidades pertenezcan al catálogo
    unknown = caps - VALID_CAPABILITIES
    if unknown:
        raise ValueError(f"Perfil '{name}' contiene capacidades inválidas: {unknown}")
    
    frozen_caps = frozenset(caps)
    VERSION_PROFILES[name] = frozen_caps
    VERSION_PROFILES[name.replace("_", "-")] = frozen_caps


def get_profile_capabilities(profile_name: str) -> FrozenSet[str]:
    """Obtiene el conjunto inmutable de capacidades permitidas para un perfil dado."""
    if profile_name not in VERSION_PROFILES:
        raise ValueError(
            f"Perfil de versión desconocido '{profile_name}'. Perfiles disponibles: {list(_BASE_PROFILES.keys())}"
        )
    return VERSION_PROFILES[profile_name]


def is_capability_allowed(profile_name: str, capability: str) -> bool:
    """Verifica si una capacidad está permitida en un perfil de versión."""
    caps = get_profile_capabilities(profile_name)
    return capability in caps
