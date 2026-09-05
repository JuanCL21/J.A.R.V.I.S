"""
tests/test_voice_session.py
Pruebas unitarias para VoiceSession (Gemini Live multimodal WebSocket).
Verifica:
1. Apertura de sesión mockeada y envío de chunks PCM.
2. Manejo de session_resumption_handle almacenado estrictamente en memoria (nunca a disco).
3. Lógica de reintento con backoff exponencial ante desconexiones.
4. Agotamiento de reintentos con transición a REPOSO y notificación de error.
5. Timeout de inactividad / silencio con retorno a REPOSO.
6. Recepción de respuesta de audio con cálculo de amplitud real y transición a HABLANDO.
"""

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from core.voice_session import (
    SILENCE_TIMEOUT_SECONDS,
    MAX_RECONNECT_ATTEMPTS,
    VoiceSession,
)


class MockLiveSession:
    """Mock asíncrono para la sesión WebSocket de Gemini Live."""

    def __init__(self, incoming_messages=None, exception_on_receive=None):
        self.incoming_messages = incoming_messages or []
        self.exception_on_receive = exception_on_receive
        self.sent_realtime_inputs = []
        self.send_realtime_input = AsyncMock(side_effect=self._mock_send_realtime)

    async def _mock_send_realtime(self, media=None, **kwargs):
        self.sent_realtime_inputs.append(media)

    async def receive(self):
        for msg in self.incoming_messages:
            yield msg
        if self.exception_on_receive:
            raise self.exception_on_receive
        # Mantener el generador abierto brevemente si no hay excepción
        while True:
            await asyncio.sleep(0.05)


class MockLiveContextManager:
    """Mock para el async context manager devuelto por client.aio.live.connect."""

    def __init__(self, session_or_sessions):
        if isinstance(session_or_sessions, list):
            self.sessions = session_or_sessions
        else:
            self.sessions = [session_or_sessions]
        self.connect_calls = []

    def connect(self, model=None, config=None):
        self.connect_calls.append({"model": model, "config": config})
        mgr = AsyncMock()

        async def _aenter(*args, **kwargs):
            if not self.sessions:
                raise ConnectionError("No hay más sesiones disponibles (simulación de fallo)")
            item = self.sessions.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        async def _aexit(*args, **kwargs):
            pass

        mgr.__aenter__ = _aenter
        mgr.__aexit__ = _aexit
        return mgr


@pytest.fixture
def mock_genai_client():
    client = MagicMock()
    client.aio = MagicMock()
    client.aio.live = MagicMock()
    return client


def test_session_start_and_send_chunk(mock_genai_client):
    """Verifica apertura de sesión y envío de chunks PCM convertidos."""
    mock_session = MockLiveSession()
    ctx_mgr = MockLiveContextManager(mock_session)
    mock_genai_client.aio.live.connect = ctx_mgr.connect

    session = VoiceSession(
        api_key="test-api-key",
        client=mock_genai_client,
        silence_timeout=5.0,
    )

    started = session.start_session()
    assert started is True
    assert session.is_active is True
    assert session.state == "escuchando"

    # Enviar array de audio (float32 normalizado)
    test_samples = np.sin(np.linspace(0, 100, 1600)).astype(np.float32)
    session.send_audio_chunk(test_samples)

    # Dar tiempo al bucle en el hilo para despachar
    for _ in range(50):
        if len(mock_session.sent_realtime_inputs) > 0:
            break
        time.sleep(0.02)

    assert len(mock_session.sent_realtime_inputs) > 0
    blob = mock_session.sent_realtime_inputs[0]
    assert blob.mime_type == "audio/pcm;rate=16000"
    assert isinstance(blob.data, bytes)
    assert len(blob.data) == len(test_samples) * 2  # 16-bit PCM = 2 bytes por muestra

    session.stop_session()
    assert session.is_active is False
    assert session.state == "reposo"


def test_session_resumption_handle_in_memory_only(mock_genai_client, tmp_path):
    """
    Verifica que el session_resumption_handle se captura en memoria
    y NUNCA se escribe en disco.
    """
    secret_handle = "live-session-resumption-handle-secret-token-xyz987"

    # Mensaje simulado con actualización de reanudación
    mock_msg = MagicMock()
    mock_msg.session_resumption_update = MagicMock()
    mock_msg.session_resumption_update.new_handle = secret_handle
    mock_msg.server_content = None

    mock_session = MockLiveSession(incoming_messages=[mock_msg])
    ctx_mgr = MockLiveContextManager(mock_session)
    mock_genai_client.aio.live.connect = ctx_mgr.connect

    session = VoiceSession(
        api_key="test-api-key",
        client=mock_genai_client,
        silence_timeout=5.0,
    )

    session.start_session()

    # Esperar a que el receptor procese el mensaje
    for _ in range(50):
        if session.session_resumption_handle == secret_handle:
            break
        time.sleep(0.02)

    assert session.session_resumption_handle == secret_handle

    session.stop_session()

    # Verificación estricta: buscar el token de reanudación en todo el directorio del proyecto
    # y en el directorio temporal para comprobar que NO fue escrito a disco.
    repo_root = Path(__file__).resolve().parent.parent
    for search_dir in [repo_root, tmp_path]:
        for root, dirs, files in os.walk(search_dir):
            # Ignorar .git y venv
            if ".git" in root or "venv" in root or "__pycache__" in root:
                continue
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in [".pyc", ".git"]:
                    continue
                try:
                    content = file_path.read_text(errors="ignore")
                    assert (
                        secret_handle not in content
                    ), f"¡El session_resumption_handle fue escrito a disco en: {file_path}!"
                except Exception:
                    pass


def test_reconnection_with_backoff_and_resumption_handle(mock_genai_client):
    """
    Verifica que ante una desconexión, VoiceSession reintenta con backoff
    e incluye el session_resumption_handle en la reconexión.
    """
    secret_handle = "prev-resumption-handle-456"

    mock_msg = MagicMock()
    mock_msg.session_resumption_update = MagicMock()
    mock_msg.session_resumption_update.new_handle = secret_handle
    mock_msg.server_content = None

    session1 = MockLiveSession(
        incoming_messages=[mock_msg],
        exception_on_receive=ConnectionResetError("Socket cerrado intempestivamente"),
    )
    session2 = MockLiveSession(incoming_messages=[])

    ctx_mgr = MockLiveContextManager([session1, session2])
    mock_genai_client.aio.live.connect = ctx_mgr.connect

    errors_reported = []
    session = VoiceSession(
        api_key="test-api-key",
        client=mock_genai_client,
        max_reconnect_attempts=2,
        reconnect_backoff_delays=(0.02, 0.04),
        on_error=lambda err: errors_reported.append(err),
    )

    session.start_session()

    # Esperar a que ocurra el fallo y la reconexión
    for _ in range(50):
        if len(ctx_mgr.connect_calls) >= 2:
            break
        time.sleep(0.02)

    assert len(ctx_mgr.connect_calls) >= 2
    # El primer intento no tenía handle
    assert ctx_mgr.connect_calls[0]["config"].session_resumption is None
    # El segundo intento debe haber usado el handle capturado
    resumption_config = ctx_mgr.connect_calls[1]["config"].session_resumption
    assert resumption_config is not None
    assert resumption_config.handle == secret_handle

    session.stop_session()


def test_reconnection_exhaustion_transitions_to_reposo(mock_genai_client):
    """
    Verifica que al agotarse el número máximo de reintentos, el estado
    vuelve a REPOSO y se notifica el error sin dejar la UI colgada.
    """
    err = ConnectionError("Fallo irrecuperable de red")
    ctx_mgr = MockLiveContextManager([err, err, err, err])
    mock_genai_client.aio.live.connect = ctx_mgr.connect

    states_recorded = []
    errors_recorded = []

    session = VoiceSession(
        api_key="test-api-key",
        client=mock_genai_client,
        max_reconnect_attempts=2,
        reconnect_backoff_delays=(0.01, 0.01),
        on_state_changed=lambda st: states_recorded.append(st),
        on_error=lambda msg: errors_recorded.append(msg),
    )

    session.start_session()

    # Esperar a que se agoten los intentos
    for _ in range(50):
        if not session.is_active and session.state == "reposo":
            break
        time.sleep(0.02)

    assert session.is_active is False
    assert session.state == "reposo"
    assert len(errors_recorded) > 0
    assert any("Se agotaron los 2 intentos de reconexión" in msg for msg in errors_recorded)


def test_silence_timeout_transitions_to_reposo(mock_genai_client):
    """
    Verifica que si no hay actividad de voz durante silence_timeout segundos,
    se cierra la captura y se vuelve a REPOSO.
    """
    mock_session = MockLiveSession()
    ctx_mgr = MockLiveContextManager(mock_session)
    mock_genai_client.aio.live.connect = ctx_mgr.connect

    silence_triggered = []
    states = []

    session = VoiceSession(
        api_key="test-api-key",
        client=mock_genai_client,
        silence_timeout=0.1,  # Timeout corto para pruebas
        on_silence_timeout=lambda: silence_triggered.append(True),
        on_state_changed=lambda s: states.append(s),
    )

    session.start_session()
    assert session.state == "escuchando"

    # Enviar un chunk de silencio (RMS bajo)
    silent_pcm = np.zeros(1600, dtype=np.float32)
    session.send_audio_chunk(silent_pcm)

    # Esperar a que se cumpla el timeout de silencio
    for _ in range(50):
        if len(silence_triggered) > 0 and session.state == "reposo":
            break
        time.sleep(0.02)

    assert len(silence_triggered) == 1
    assert session.state == "reposo"
    assert session.is_active is False


def test_response_audio_reception_and_real_amplitude(mock_genai_client):
    """
    Verifica que al recibir audio de respuesta de Gemini Live, se calcula
    la amplitud real (no una envolvente sintética) y se transiciona a HABLANDO.
    """
    # Generar muestras PCM 16-bit reales
    raw_pcm16 = (np.sin(np.linspace(0, 10, 800)) * 20000).astype(np.int16).tobytes()

    mock_part = MagicMock()
    mock_part.inline_data = MagicMock()
    mock_part.inline_data.data = raw_pcm16
    mock_part.text = None

    mock_server_content = MagicMock()
    mock_server_content.model_turn = MagicMock()
    mock_server_content.model_turn.parts = [mock_part]
    mock_server_content.turn_complete = False

    mock_msg = MagicMock()
    mock_msg.session_resumption_update = None
    mock_msg.server_content = mock_server_content

    mock_session = MockLiveSession(incoming_messages=[mock_msg])
    ctx_mgr = MockLiveContextManager(mock_session)
    mock_genai_client.aio.live.connect = ctx_mgr.connect

    audio_outputs = []
    states = []

    session = VoiceSession(
        api_key="test-api-key",
        client=mock_genai_client,
        silence_timeout=5.0,
        on_audio_output=lambda data, amp: audio_outputs.append((data, amp)),
        on_state_changed=lambda s: states.append(s),
    )

    session.start_session()

    for _ in range(50):
        if len(audio_outputs) > 0:
            break
        time.sleep(0.02)

    assert len(audio_outputs) > 0
    received_bytes, computed_amplitude = audio_outputs[0]
    assert received_bytes == raw_pcm16
    # La amplitud debe corresponder a ~20000 / 32768 = ~0.61 (amplitud real)
    assert 0.5 < computed_amplitude < 0.7
    assert session.state == "hablando"

    session.stop_session()


def test_missing_api_key_fails_gracefully():
    """Verifica que sin API Key ni en secrets ni entorno, se notifique el error sin colapsar."""
    with patch("core.voice_session.get_secret", return_value=None), patch.dict(os.environ, {}, clear=True):
        errors = []
        session = VoiceSession(
            api_key=None,
            on_error=lambda err: errors.append(err),
        )
        started = session.start_session()
        assert started is False
        assert session.state == "reposo"
        assert len(errors) == 1
        assert "GEMINI_API_KEY no encontrada" in errors[0]
