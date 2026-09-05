"""
Tests para core/audio_devices.py (sondeo y deduplicación de interfaces de audio).
Verifica:
1. Deduplicación de dispositivos de entrada con nombres equivalentes bajo distintas APIs.
2. Deduplicación de dispositivos de salida.
3. Extracción de nombres canónicos limpios.
4. Identificación correcta del dispositivo por defecto.
"""

from unittest.mock import MagicMock
import pytest

import sounddevice as sd
from core.audio_devices import (
    AudioDeviceInfo,
    list_input_devices,
    list_output_devices,
    get_default_input_device,
    get_default_output_device,
)


@pytest.fixture
def mock_devices_with_duplicates(monkeypatch):
    """
    Simula una lista devuelta por sounddevice.query_devices() que incluye
    múltiples duplicados del mismo micrófono y altavoz bajo distintas Host APIs (ALSA, Pulse, etc.).
    """
    mock_list = [
        # Dispositivo 0: Micrófono analógico principal (ALSA)
        {
            "name": "HDA Intel PCH: ALC255 Analog (hw:0,0)",
            "index": 0,
            "hostapi": 0,
            "max_input_channels": 2,
            "max_output_channels": 2,
            "default_samplerate": 48000.0,
        },
        # Dispositivo 1: DUPLICADO del micrófono analógico bajo PulseAudio
        {
            "name": "HDA Intel PCH: ALC255 Analog",
            "index": 1,
            "hostapi": 1,
            "max_input_channels": 2,
            "max_output_channels": 2,
            "default_samplerate": 48000.0,
        },
        # Dispositivo 2: Micrófono USB externo (único)
        {
            "name": "USB Condenser Microphone",
            "index": 2,
            "hostapi": 0,
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 44100.0,
        },
        # Dispositivo 3: Salida HDMI (solo salida)
        {
            "name": "HDA NVidia: HDMI 0 (hw:1,3)",
            "index": 3,
            "hostapi": 0,
            "max_input_channels": 0,
            "max_output_channels": 8,
            "default_samplerate": 48000.0,
        },
        # Dispositivo 4: DUPLICADO Salida HDMI bajo otra API
        {
            "name": "HDA NVidia: HDMI 0",
            "index": 4,
            "hostapi": 1,
            "max_input_channels": 0,
            "max_output_channels": 8,
            "default_samplerate": 48000.0,
        },
    ]

    mock_hostapis = [
        {"name": "ALSA", "devices": [0, 2, 3], "default_input_device": 0, "default_output_device": 3},
        {"name": "PulseAudio", "devices": [1, 4], "default_input_device": 1, "default_output_device": 4},
    ]

    monkeypatch.setattr(sd, "query_devices", lambda: mock_list)
    monkeypatch.setattr(sd, "query_hostapis", lambda: mock_hostapis)
    monkeypatch.setattr(sd.default, "device", (0, 3))

    return mock_list


def test_list_input_devices_deduplication(mock_devices_with_duplicates):
    """
    Verifica que list_input_devices(deduplicate=True) reduzca los duplicados
    reconociendo el nombre canónico y descartando entradas secundarias.
    """
    # Con deduplicación
    inputs_dedup = list_input_devices(deduplicate=True)
    # Deben quedar solo 2 dispositivos de entrada únicos: ALC255 Analog y USB Condenser Microphone
    assert len(inputs_dedup) == 2

    names = [d.canonical_name for d in inputs_dedup]
    assert "HDA Intel PCH: ALC255 Analog" in names
    assert "USB Condenser Microphone" in names

    # Sin deduplicación deberían ser 3 entradas con max_input_channels > 0
    inputs_all = list_input_devices(deduplicate=False)
    assert len(inputs_all) == 3


def test_list_output_devices_deduplication(mock_devices_with_duplicates):
    """
    Verifica que list_output_devices(deduplicate=True) descarte dispositivos solo de entrada
    y reduzca los duplicados de salida.
    """
    outputs_dedup = list_output_devices(deduplicate=True)
    # Dispositivos de salida únicos: ALC255 Analog y HDMI 0
    assert len(outputs_dedup) == 2

    canonical_names = [d.canonical_name for d in outputs_dedup]
    assert "HDA Intel PCH: ALC255 Analog" in canonical_names
    assert "HDA NVidia: HDMI 0" in canonical_names


def test_default_device_detection(mock_devices_with_duplicates):
    """Verifica que se detecten correctamente los dispositivos por defecto marcados."""
    default_in = get_default_input_device()
    assert default_in is not None
    assert default_in.index == 0
    assert default_in.is_default is True

    default_out = get_default_output_device()
    assert default_out is not None
    assert default_out.index == 3
    assert default_out.is_default is True
