"""
Sondeo y gestión de dispositivos de audio reales (spec captura de micrófono).
Utiliza sounddevice para consultar interfaces de entrada y salida, descartando
duplicados generados por múltiples host APIs y exponiendo nombres canónicos limpios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import sounddevice as sd
except ImportError:
    sd = None


@dataclass(frozen=True)
class AudioDeviceInfo:
    """Información canónica y estructurada de un dispositivo de audio."""
    index: int
    name: str
    canonical_name: str
    hostapi: int
    hostapi_name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_default: bool = False


def _canonicalize_device_name(raw_name: str) -> str:
    """
    Genera un nombre canónico limpio eliminando sufijos de host API,
    índices de hardware redundantes o etiquetas genéricas.
    """
    if not raw_name:
        return "Dispositivo desconocido"

    cleaned = raw_name.strip()
    # Eliminar sufijos como (hw:0,0) o similares si se duplican
    cleaned = re.sub(r"\s*\(hw:\d+,\d+\)", "", cleaned)
    # Limpiar espacios múltiples
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or raw_name.strip()


def _get_hostapi_name(hostapis: Any, hostapi_index: int) -> str:
    """Obtiene el nombre legible de la Host API (ALSA, WASAPI, CoreAudio, etc.)."""
    if not hostapis:
        return "Desconocido"
    try:
        if isinstance(hostapis, (list, tuple)) and 0 <= hostapi_index < len(hostapis):
            item = hostapis[hostapi_index]
            if isinstance(item, dict):
                return item.get("name", "Desconocido")
    except Exception:
        pass
    return f"API #{hostapi_index}"


def list_input_devices(deduplicate: bool = True) -> List[AudioDeviceInfo]:
    """
    Lista todos los dispositivos de entrada (micrófonos) disponibles.
    Si deduplicate=True, descarta dispositivos con el mismo nombre canónico
    provenientes de host APIs secundarias.
    """
    if sd is None:
        return []

    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_devs = sd.default.device
        default_input_idx = default_devs[0] if default_devs is not None else -1
    except Exception:
        return []

    if not isinstance(devices, (list, tuple)):
        # Si devuelve un solo dispositivo o formato DeviceList
        try:
            devices = list(devices)
        except Exception:
            return []

    results: List[AudioDeviceInfo] = []
    seen_canonical_names: set[str] = set()

    for idx, dev in enumerate(devices):
        if not isinstance(dev, dict):
            continue

        max_in = dev.get("max_input_channels", 0)
        if max_in <= 0:
            continue

        raw_name = dev.get("name", f"Dispositivo #{idx}")
        canonical = _canonicalize_device_name(raw_name)

        if deduplicate:
            # Normalizar para deduplicar (minúsculas, sin espacios extras)
            norm_key = canonical.lower()
            if norm_key in seen_canonical_names:
                continue
            seen_canonical_names.add(norm_key)

        hostapi_idx = dev.get("hostapi", 0)
        hostapi_str = _get_hostapi_name(hostapis, hostapi_idx)
        is_default = (idx == default_input_idx)

        results.append(
            AudioDeviceInfo(
                index=dev.get("index", idx),
                name=raw_name,
                canonical_name=canonical,
                hostapi=hostapi_idx,
                hostapi_name=hostapi_str,
                max_input_channels=max_in,
                max_output_channels=dev.get("max_output_channels", 0),
                default_samplerate=float(dev.get("default_samplerate", 44100.0)),
                is_default=is_default,
            )
        )

    return results


def list_output_devices(deduplicate: bool = True) -> List[AudioDeviceInfo]:
    """
    Lista todos los dispositivos de salida (altavoces/auriculares) disponibles.
    Si deduplicate=True, descarta duplicados por nombre canónico.
    """
    if sd is None:
        return []

    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_devs = sd.default.device
        default_output_idx = default_devs[1] if default_devs is not None else -1
    except Exception:
        return []

    if not isinstance(devices, (list, tuple)):
        try:
            devices = list(devices)
        except Exception:
            return []

    results: List[AudioDeviceInfo] = []
    seen_canonical_names: set[str] = set()

    for idx, dev in enumerate(devices):
        if not isinstance(dev, dict):
            continue

        max_out = dev.get("max_output_channels", 0)
        if max_out <= 0:
            continue

        raw_name = dev.get("name", f"Dispositivo #{idx}")
        canonical = _canonicalize_device_name(raw_name)

        if deduplicate:
            norm_key = canonical.lower()
            if norm_key in seen_canonical_names:
                continue
            seen_canonical_names.add(norm_key)

        hostapi_idx = dev.get("hostapi", 0)
        hostapi_str = _get_hostapi_name(hostapis, hostapi_idx)
        is_default = (idx == default_output_idx)

        results.append(
            AudioDeviceInfo(
                index=dev.get("index", idx),
                name=raw_name,
                canonical_name=canonical,
                hostapi=hostapi_idx,
                hostapi_name=hostapi_str,
                max_input_channels=dev.get("max_input_channels", 0),
                max_output_channels=max_out,
                default_samplerate=float(dev.get("default_samplerate", 44100.0)),
                is_default=is_default,
            )
        )

    return results


def get_default_input_device() -> Optional[AudioDeviceInfo]:
    """Retorna el dispositivo de entrada por defecto del sistema."""
    devices = list_input_devices(deduplicate=False)
    for d in devices:
        if d.is_default:
            return d
    return devices[0] if devices else None


def get_default_output_device() -> Optional[AudioDeviceInfo]:
    """Retorna el dispositivo de salida por defecto del sistema."""
    devices = list_output_devices(deduplicate=False)
    for d in devices:
        if d.is_default:
            return d
    return devices[0] if devices else None
