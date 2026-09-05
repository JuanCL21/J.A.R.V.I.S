"""
ui/test_app_audio_capture.py
Pruebas de integración para la captura de audio en ui/app.py.
Verifica:
1. Al entrar en estado ESCUCHANDO se abre el stream de captura mockeado de sounddevice.
2. Al salir de ESCUCHANDO se detiene y cierra el stream.
3. El callback de audio no toca widgets de Qt directamente, sino que se comunica exclusivamente
   a través de señales Qt (pyqtSignal) seguras entre hilos.
4. El procesamiento del chunk en el hilo principal alimenta el visualizador reactivo y la sesión de voz.
5. La respuesta de audio de Gemini Live actualiza el visualizador con amplitud real.
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ui.app import JarvisMainWindow
from ui.audio_visualizer import VisualizerState


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    with patch("core.voice_session.get_secret", return_value="dummy_gemini_key"):
        win = JarvisMainWindow()
        yield win
        win.close()


def test_entering_escuchando_opens_capture_stream(window, qapp):
    """Verifica que al entrar en estado ESCUCHANDO se abre e inicia el stream de captura."""
    mock_stream = MagicMock()

    with patch("sounddevice.InputStream", return_value=mock_stream) as mock_input_stream_cls, \
         patch.object(window.voice_session, "start_session", return_value=True) as mock_start_voice:

        assert window.audio_stream is None
        window.switch_mode(VisualizerState.ESCUCHANDO)
        qapp.processEvents()

        # Comprobar que InputStream fue invocado con los parámetros correctos
        mock_input_stream_cls.assert_called_once()
        kwargs = mock_input_stream_cls.call_args.kwargs
        assert kwargs["samplerate"] == 16000
        assert kwargs["channels"] == 1
        assert kwargs["callback"] == window._sounddevice_input_callback

        # Comprobar que start() del stream fue ejecutado
        mock_stream.start.assert_called_once()
        assert window.audio_stream == mock_stream
        mock_start_voice.assert_called_once()


def test_leaving_escuchando_stops_and_closes_stream(window, qapp):
    """Verifica que al salir de ESCUCHANDO hacia REPOSO se detiene y cierra el stream."""
    mock_stream = MagicMock()

    with patch("sounddevice.InputStream", return_value=mock_stream), \
         patch.object(window.voice_session, "start_session", return_value=True), \
         patch.object(window.voice_session, "stop_session") as mock_stop_voice:

        window.switch_mode(VisualizerState.ESCUCHANDO)
        assert window.audio_stream is not None

        window.switch_mode(VisualizerState.REPOSO)
        qapp.processEvents()

        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert window.audio_stream is None
        mock_stop_voice.assert_called_once()


def test_sounddevice_callback_emits_signal_without_direct_widget_access(window, qapp):
    """
    Verifica que el callback de audio ejecuta desde un hilo separado, NO toca
    widgets de Qt directamente, y la comunicación pasa estrictamente por la señal Qt.
    """
    signal_received_chunks = []
    window.audio_bridge.sig_audio_chunk.connect(lambda ch: signal_received_chunks.append(ch))

    # Spy sobre el visualizador para comprobar que el callback no lo llama de forma síncrona/directa
    direct_widget_called = False
    original_feed = window.visualizer.feed_audio_samples

    def spy_feed(*args, **kwargs):
        nonlocal direct_widget_called
        # Comprobar si fue llamado desde el hilo de audio secundario
        if threading.current_thread() != threading.main_thread():
            direct_widget_called = True
        return original_feed(*args, **kwargs)

    window.visualizer.feed_audio_samples = spy_feed

    # Datos de prueba
    test_chunk = np.ones((512, 1), dtype=np.float32) * 0.25

    # Simular la ejecución del callback desde un hilo secundario (como hace PortAudio)
    callback_executed = threading.Event()

    def audio_thread_worker():
        window._sounddevice_input_callback(test_chunk, 512, None, None)
        callback_executed.set()

    t = threading.Thread(target=audio_thread_worker, name="PortAudioMockThread")
    t.start()
    t.join(timeout=1.0)

    assert callback_executed.is_set()
    # Confirmar que el callback de audio NO tocó el widget directamente desde el hilo secundario
    assert direct_widget_called is False

    # Procesar la cola de eventos de Qt en el hilo principal
    qapp.processEvents()

    # Confirmar que la señal fue recibida y entregó los datos al hilo principal
    assert len(signal_received_chunks) == 1
    np.testing.assert_array_equal(signal_received_chunks[0], test_chunk)


def test_captured_chunk_feeds_visualizer_and_voice_session(window, qapp):
    """Verifica que el slot principal alimenta feed_audio_samples y send_audio_chunk."""
    window.visualizer.set_state(VisualizerState.ESCUCHANDO)

    with patch.object(window.visualizer, "feed_audio_samples") as mock_feed, \
         patch.object(window.voice_session, "send_audio_chunk") as mock_send:

        window.voice_session._is_active = True

        test_data = np.linspace(-0.5, 0.5, 256, dtype=np.float32)
        # Emitir señal
        window.audio_bridge.sig_audio_chunk.emit(test_data)
        qapp.processEvents()

        mock_feed.assert_called_once()
        mock_send.assert_called_once()


def test_voice_audio_output_updates_visualizer_real_amplitude(window, qapp):
    """
    Verifica que al recibir audio de respuesta de Gemini Live, el visualizador
    transiciona a HABLANDO y recibe la amplitud real medida.
    """
    assert window.visualizer.state == VisualizerState.REPOSO

    real_amplitude = 0.72
    dummy_pcm = b"\x00" * 320

    with patch.object(window.visualizer, "feed_output_amplitude") as mock_amp_feed:
        # Emitir señal como lo hace el worker de voice_session
        window.voice_bridge.sig_audio_output.emit(dummy_pcm, real_amplitude)
        qapp.processEvents()

        assert window.visualizer.state == VisualizerState.HABLANDO
        mock_amp_feed.assert_called_once_with(real_amplitude)
