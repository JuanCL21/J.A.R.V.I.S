"""
Catálogo cerrado de capacidades del sistema JARVIS.
Cualquier capacidad declarada en un manifiesto que no figure aquí causará un ValueError en la carga.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Set


@dataclass(frozen=True)
class CapabilityDefinition:
    name: str
    description: str
    requires_confirmation: bool = False


# Catálogo cerrado y definitivo de capacidades
CAPABILITY_CATALOG: Dict[str, CapabilityDefinition] = {
    "system_info": CapabilityDefinition(
        name="system_info",
        description="Lectura de información del sistema, reloj, estado y métricas básicas",
        requires_confirmation=False,
    ),
    "filesystem_read": CapabilityDefinition(
        name="filesystem_read",
        description="Lectura de archivos dentro del sandbox autorizado",
        requires_confirmation=False,
    ),
    "filesystem_write": CapabilityDefinition(
        name="filesystem_write",
        description="Escritura, modificación o borrado de archivos dentro del sandbox",
        requires_confirmation=True,
    ),
    "code_execution": CapabilityDefinition(
        name="code_execution",
        description="Ejecución de código arbitrario o scripts en entorno aislado",
        requires_confirmation=True,
    ),
    "network_access": CapabilityDefinition(
        name="network_access",
        description="Peticiones de red e integración con APIs externas",
        requires_confirmation=False,
    ),
    "device_management": CapabilityDefinition(
        name="device_management",
        description="Gestión, emparejamiento y control de dispositivos vinculados",
        requires_confirmation=True,
    ),
    "audio_synthesis": CapabilityDefinition(
        name="audio_synthesis",
        description="Generación de voz y síntesis de audio (TTS)",
        requires_confirmation=False,
    ),
    "audio_capture": CapabilityDefinition(
        name="audio_capture",
        description="Captura de micrófono y reconocimiento de voz (STT)",
        requires_confirmation=False,
    ),
    "notify_user": CapabilityDefinition(
        name="notify_user",
        description="Envío de notificaciones al usuario local o interfaz activa",
        requires_confirmation=False,
    ),
    "telegram_send": CapabilityDefinition(
        name="telegram_send",
        description="Envío de mensajes y alertas a través del bot de Telegram",
        requires_confirmation=False,
    ),
}

VALID_CAPABILITIES: Set[str] = set(CAPABILITY_CATALOG.keys())


def is_valid_capability(name: str) -> bool:
    """Verifica si una capacidad pertenece al catálogo cerrado."""
    return name in VALID_CAPABILITIES


def capability_requires_confirmation(name: str) -> bool:
    """Indica si una capacidad requiere confirmación explícita del usuario."""
    cap = CAPABILITY_CATALOG.get(name)
    if not cap:
        raise ValueError(f"Capacidad desconocida: '{name}'")
    return cap.requires_confirmation


def validate_capabilities(capabilities: Iterable[str]) -> None:
    """
    Valida una lista/conjunto de capacidades contra el catálogo cerrado.
    Lanza ValueError si alguna no existe en el catálogo.
    """
    for cap in capabilities:
        if not is_valid_capability(cap):
            raise ValueError(
                f"Capacidad inválida '{cap}' no reconocida en el catálogo cerrado de capacidades."
            )
