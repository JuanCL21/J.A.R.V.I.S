"""
core/voice_session.py
Gestiona la sesión WebSocket con Gemini Live (google-genai, API multimodal bidireccional).
Manejo de streaming de audio PCM, recepción de respuestas de audio y texto, reanudación
de sesión con handle en memoria y reconexión con retroceso exponencial (backoff).
"""

import asyncio
import logging
import math
import os
import threading
import time
from typing import Any, Callable, Optional, Sequence

import numpy as np
from google import genai
from google.genai import types

from core.secrets import get_secret

logger = logging.getLogger("jarvis.voice_session")

SILENCE_TIMEOUT_SECONDS: float = 8.0
MAX_RECONNECT_ATTEMPTS: int = 3
RECONNECT_BACKOFF_DELAYS: Sequence[float] = (1.0, 2.0, 4.0)
DEFAULT_MODEL: str = "gemini-2.0-flash-exp"
DEFAULT_SAMPLE_RATE: int = 16000
SILENCE_RMS_THRESHOLD: float = 0.01


class VoiceSession:
    """
    Controlador de sesión de voz bidireccional con Gemini Live.
    Mantiene la conexión WebSocket en un hilo secundario con un bucle de eventos asyncio,
    garantizando que ninguna operación de red o audio bloquee el hilo principal de la UI.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        silence_timeout: float = SILENCE_TIMEOUT_SECONDS,
        max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS,
        reconnect_backoff_delays: Sequence[float] = RECONNECT_BACKOFF_DELAYS,
        silence_rms_threshold: float = SILENCE_RMS_THRESHOLD,
        client: Optional[Any] = None,
        on_state_changed: Optional[Callable[[str], None]] = None,
        on_audio_output: Optional[Callable[[bytes, float], None]] = None,
        on_text_output: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_silence_timeout: Optional[Callable[[], None]] = None,
    ):
        # API Key obtenida de forma segura: nunca serializada ni logueada
        self._api_key = api_key or get_secret("GEMINI_API_KEY")
        self.model = model
        self.sample_rate = sample_rate
        self.silence_timeout = silence_timeout
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_backoff_delays = list(reconnect_backoff_delays)
        self.silence_rms_threshold = silence_rms_threshold

        # Manejo de reanudación de sesión: ÚNICAMENTE en memoria (atributo de instancia, nunca a disco)
        self._session_resumption_handle: Optional[str] = None

        # Cliente Gemini
        self._client = client

        # Callbacks para comunicación sin bloqueo con la capa superior
        self.on_state_changed = on_state_changed
        self.on_audio_output = on_audio_output
        self.on_text_output = on_text_output
        self.on_error = on_error
        self.on_silence_timeout = on_silence_timeout

        # Estado interno
        self._is_active: bool = False
        self._current_state: str = "reposo"
        self._last_speech_time: float = time.monotonic()

        # Componentes de hilo y asincronía
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._audio_queue: Optional[asyncio.Queue] = None
        self._pending_audio_chunks: list[bytes] = []
        self._session_task: Optional[asyncio.Task] = None
        self._connected_event = threading.Event()
        self._lock = threading.Lock()

    @property
    def session_resumption_handle(self) -> Optional[str]:
        """Devuelve el handle de reanudación de sesión actual (almacenado solo en memoria)."""
        return self._session_resumption_handle

    @property
    def is_active(self) -> bool:
        """Indica si la sesión está actualmente en ejecución."""
        return self._is_active

    @property
    def state(self) -> str:
        """Estado actual ('reposo', 'escuchando', 'hablando')."""
        return self._current_state

    def _set_state(self, new_state: str) -> None:
        """Actualiza el estado interno y notifica al callback si cambió."""
        if self._current_state != new_state:
            self._current_state = new_state
            if self.on_state_changed:
                try:
                    self.on_state_changed(new_state)
                except Exception as e:
                    logger.warning(f"Error en callback on_state_changed: {e}")

    def start_session(self) -> bool:
        """
        Inicia la sesión de voz con Gemini Live en un hilo dedicado.
        Retorna True si el inicio fue exitoso, False si no hay credenciales.
        """
        with self._lock:
            if self._is_active:
                logger.debug("La sesión de voz ya se encuentra activa.")
                return True

            if not self._client and not self._api_key:
                err_msg = "GEMINI_API_KEY no encontrada en secretos ni variables de entorno."
                logger.error(err_msg)
                if self.on_error:
                    self.on_error(err_msg)
                self._set_state("reposo")
                return False

            if not self._client:
                self._client = genai.Client(api_key=self._api_key)

            self._is_active = True
            self._connected_event.clear()
            self._last_speech_time = time.monotonic()
            self._set_state("escuchando")

            self._thread = threading.Thread(
                target=self._run_event_loop,
                name="JarvisVoiceSessionThread",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop_session(self) -> None:
        """Detiene la sesión y limpia los recursos del hilo secundario."""
        with self._lock:
            if not self._is_active and not (self._thread and self._thread.is_alive()):
                self._set_state("reposo")
                return

            self._is_active = False

            if self._loop and self._loop.is_running():
                # Notificar a la cola y cancelar tareas en el bucle asyncio
                def _shutdown():
                    if self._audio_queue:
                        self._audio_queue.put_nowait(None)
                    if self._session_task and not self._session_task.done():
                        self._session_task.cancel()

                self._loop.call_soon_threadsafe(_shutdown)

            self._set_state("reposo")

        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def wait_for_connected(self, timeout: float = 2.0) -> bool:
        """Espera a que la conexión WebSocket con Gemini Live esté activa."""
        return self._connected_event.wait(timeout=timeout)

    def send_audio_chunk(self, data: bytes | np.ndarray) -> None:
        """
        Envía un fragmento de audio PCM (16kHz mono) para streaming a Gemini Live.
        Convierte datos numpy a bytes PCM16 si es necesario y monitorea actividad de voz.
        """
        if not self._is_active:
            return

        # Conversión a PCM 16-bit little-endian
        if isinstance(data, np.ndarray):
            if np.issubdtype(data.dtype, np.floating):
                # Float normalizado [-1.0, 1.0] -> int16
                clipped = np.clip(data, -1.0, 1.0)
                int16_data = (clipped * 32767.0).astype(np.int16)
                pcm_bytes = int16_data.tobytes()
                # Detección de energía RMS
                rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
            elif data.dtype == np.int16:
                pcm_bytes = data.tobytes()
                norm = data.astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(norm**2)))
            else:
                int16_data = data.astype(np.int16)
                pcm_bytes = int16_data.tobytes()
                rms = 0.05
        elif isinstance(data, bytes):
            pcm_bytes = data
            try:
                samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(samples**2))) if len(samples) > 0 else 0.0
            except Exception:
                rms = 0.05
        else:
            return

        # Actualizar temporizador de silencio si se detecta energía por encima del umbral
        if rms >= self.silence_rms_threshold:
            self._last_speech_time = time.monotonic()
            # Barge-in: interrupción en tiempo real cuando el usuario habla mientras JARVIS emite respuesta
            if self._current_state in ("hablando", "pensando"):
                logger.info("Barge-in detectado: voz del usuario durante respuesta. Interrumpiendo a 'escuchando'.")
                self._set_state("escuchando")

        with self._lock:
            if not (self._loop and self._loop.is_running() and self._audio_queue):
                self._pending_audio_chunks.append(pcm_bytes)
                return

        try:
            self._loop.call_soon_threadsafe(self._audio_queue.put_nowait, pcm_bytes)
        except Exception as e:
            logger.debug(f"No se pudo encolar chunk de audio: {e}")

    def interrupt(self) -> None:
        """
        Interrumpe de inmediato la emisión del modelo (Barge-in / Gemini Live)
        y retorna la sesión al estado 'escuchando'.
        """
        logger.info("Interrupción explícita solicitada (Barge-in).")
        self._last_speech_time = time.monotonic()
        self._set_state("escuchando")

    def _run_event_loop(self) -> None:
        """Bucle de eventos asyncio en hilo secundario."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._audio_queue = asyncio.Queue()

        try:
            self._loop.run_until_complete(self._main_session_coro())
        except Exception as e:
            logger.error(f"Excepción en bucle de voz: {e}")
        finally:
            try:
                # Cancelar tareas pendientes
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:
                pass
            self._loop.close()
            self._loop = None
            self._set_state("reposo")

    async def _main_session_coro(self) -> None:
        """
        Ciclo principal de sesión con soporte para reconexión y retroceso exponencial (backoff).
        """
        reconnect_attempts = 0

        while self._is_active:
            try:
                # Configurar LiveConnectConfig con sesión previa si existe en memoria
                config_kwargs: dict[str, Any] = {
                    "response_modalities": ["AUDIO"],
                }
                if self._session_resumption_handle:
                    config_kwargs["session_resumption"] = types.SessionResumptionConfig(
                        handle=self._session_resumption_handle,
                        transparent=True,
                    )
                    logger.info("Intentando reanudar sesión con handle previo en memoria.")

                config = types.LiveConnectConfig(**config_kwargs)

                logger.info(f"Iniciando conexión WebSocket con Gemini Live (modelo={self.model})...")
                async with self._client.aio.live.connect(model=self.model, config=config) as session:
                    reconnect_attempts = 0
                    self._connected_event.set()
                    logger.info("Conexión WebSocket establecida con éxito.")

                    # Despachar chunks acumulados antes de que la conexión estuviera lista
                    with self._lock:
                        while self._pending_audio_chunks:
                            pending_chunk = self._pending_audio_chunks.pop(0)
                            self._audio_queue.put_nowait(pending_chunk)

                    sender_task = asyncio.create_task(self._sender_loop(session))
                    receiver_task = asyncio.create_task(self._receiver_loop(session))
                    silence_task = asyncio.create_task(self._silence_monitor_loop())

                    done, pending = await asyncio.wait(
                        [sender_task, receiver_task, silence_task],
                        return_when=asyncio.FIRST_EXCEPTION,
                    )

                    for t in pending:
                        t.cancel()

                    for t in done:
                        exc = t.exception()
                        if exc and not isinstance(exc, asyncio.CancelledError):
                            raise exc

                    # Si salió sin excepciones (ej. por stop_session o timeout)
                    break

            except (asyncio.CancelledError, GeneratorExit):
                break
            except Exception as exc:
                if not self._is_active:
                    break

                reconnect_attempts += 1
                if reconnect_attempts <= self.max_reconnect_attempts:
                    delay_idx = min(reconnect_attempts - 1, len(self.reconnect_backoff_delays) - 1)
                    delay = self.reconnect_backoff_delays[delay_idx]
                    logger.warning(
                        f"Fallo de conexión WebSocket con Gemini Live ({exc}). "
                        f"Reintentando {reconnect_attempts}/{self.max_reconnect_attempts} en {delay}s..."
                    )
                    if self.on_error:
                        self.on_error(f"Fallo de red ({exc}). Reintento {reconnect_attempts}/{self.max_reconnect_attempts} en {delay}s...")

                    await asyncio.sleep(delay)
                else:
                    err = (
                        f"Se agotaron los {self.max_reconnect_attempts} intentos de reconexión con Gemini Live. "
                        f"Último error: {exc}"
                    )
                    logger.error(err)
                    if self.on_error:
                        self.on_error(err)
                    self._set_state("reposo")
                    self._is_active = False
                    break

    async def _sender_loop(self, session: Any) -> None:
        """Envía fragmentos de audio desde la cola hacia el WebSocket de Gemini Live."""
        while self._is_active:
            pcm_bytes = await self._audio_queue.get()
            if pcm_bytes is None:
                break

            try:
                blob = types.Blob(
                    data=pcm_bytes,
                    mime_type=f"audio/pcm;rate={self.sample_rate}",
                )
                await session.send_realtime_input(media=blob)
            except Exception as e:
                logger.warning(f"Error al enviar chunk por WebSocket: {e}")
                raise

    async def _receiver_loop(self, session: Any) -> None:
        """Recibe mensajes multimodales de respuesta desde Gemini Live."""
        async for message in session.receive():
            if not self._is_active:
                break

            # 1. Manejo de reanudación de sesión: captura handle en memoria
            if getattr(message, "session_resumption_update", None):
                upd = message.session_resumption_update
                new_handle = getattr(upd, "new_handle", None)
                if new_handle:
                    self._session_resumption_handle = new_handle
                    logger.debug("session_resumption_handle actualizado en memoria.")

            # 2. Manejo de contenido del servidor
            server_content = getattr(message, "server_content", None)
            if server_content:
                # Detección de interrupción confirmada por el servidor Gemini Live
                if getattr(server_content, "interrupted", False):
                    logger.info("Gemini Live confirmó interrupción (barge-in).")
                    self._set_state("escuchando")

                model_turn = getattr(server_content, "model_turn", None)
                if model_turn and getattr(model_turn, "parts", None):
                    for part in model_turn.parts:
                        # Audio inline
                        inline_data = getattr(part, "inline_data", None)
                        if inline_data and getattr(inline_data, "data", None):
                            raw_audio = inline_data.data
                            try:
                                pcm16 = np.frombuffer(raw_audio, dtype=np.int16)
                                if len(pcm16) > 0:
                                    amplitude = float(np.max(np.abs(pcm16))) / 32768.0
                                else:
                                    amplitude = 0.0
                            except Exception:
                                amplitude = 0.5

                            self._set_state("hablando")
                            if self.on_audio_output:
                                self.on_audio_output(raw_audio, amplitude)

                        # Texto
                        text = getattr(part, "text", None)
                        if text:
                            if self.on_text_output:
                                self.on_text_output(text)

                # Si el modelo terminó de hablar
                if getattr(server_content, "turn_complete", False):
                    if self._is_active:
                        self._set_state("escuchando")

    async def _silence_monitor_loop(self) -> None:
        """
        Monitorea el tiempo de inactividad de voz del usuario en estado ESCUCHANDO.
        Si supera silence_timeout segundos, cierra la captura y retorna a REPOSO.
        """
        while self._is_active:
            await asyncio.sleep(0.5)
            if self._current_state == "escuchando":
                elapsed = time.monotonic() - self._last_speech_time
                if elapsed >= self.silence_timeout:
                    logger.info(
                        f"Timeout de captura: {elapsed:.1f}s sin actividad de voz (límite: {self.silence_timeout}s). "
                        "Cerrando captura y volviendo a REPOSO."
                    )
                    if self.on_silence_timeout:
                        try:
                            self.on_silence_timeout()
                        except Exception as e:
                            logger.warning(f"Error en on_silence_timeout: {e}")

                    self._set_state("reposo")
                    self._is_active = False
                    break
