"""
Módulo de Interfaz de Usuario (UI) de JARVIS.
Exporta el visualizador de audio reactivo y utilidades de renderizado 2D/3D.
"""

from .audio_visualizer import ReactiveAudioVisualizer, VisualizerState
from .confirmation_dialog import ConfirmationDialog, ConfirmationRequest
from .plugin_catalog import PluginCatalogScreen
from .plugin_management_dialog import PluginManagementDialog
from .app import JarvisMainWindow

from .toast_notification import ToastManager, ToastNotification
from .audit_viewer_screen import AuditViewerScreen, AuditViewerDialog, mask_sensitive_data

__all__ = [
    "ReactiveAudioVisualizer",
    "VisualizerState",
    "ConfirmationDialog",
    "ConfirmationRequest",
    "PluginCatalogScreen",
    "PluginManagementDialog",
    "JarvisMainWindow",
    "ToastNotification",
    "ToastManager",
    "AuditViewerScreen",
    "AuditViewerDialog",
    "mask_sensitive_data",
]


