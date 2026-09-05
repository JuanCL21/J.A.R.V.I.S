"""
Diálogo Modal de Gestión de Plugins para JARVIS (spec 4.1, 4.3 y 4.4).

Embebe la pantalla de catálogo curado (PluginCatalogScreen) y el Modo Avanzado
dentro de un diálogo modal invocado desde el ícono de escudo del HUD principal.

Reglas de diseño y seguridad:
- El diálogo es modal (QDialog.exec() bloquea de forma limpia la acción sin congelar
  el bucle de eventos ni los timers del visualizador 3D de fondo).
- Modo Avanzado (spec 4.4):
  - Visualmente diferenciado con acentos ámbar/rojo de riesgo en los bordes.
  - Oculto/cerrado por defecto detrás de un toggle de advertencia.
  - Requiere resolver el commit SHA-1 completo antes de habilitar la instalación.
  - Valida fail-closed el esquema de la URL antes de cualquier subproceso git.
  - "Promover a curado" solo es visible para plugins con status 'no_verificado'
    y exige confirmación modal con identidad obligatoria de reviewed_by.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.plugin_installer import PluginInstaller, resolve_git_ref, validate_source_url
from core.plugin_registry import PluginRegistry
from ui.plugin_catalog import PluginCatalogScreen


class PromoteCuratedDialog(QDialog):
    """
    Diálogo secundario modal para confirmar la promoción de un plugin a 'curado'.
    Exige obligatoriamente la identidad del revisor antes de autorizar el cambio.
    """

    def __init__(self, parent: Optional[QWidget], plugin_id: str):
        super().__init__(parent)
        self.setWindowTitle("CONFIRMAR PROMOCIÓN A CURADO")
        self.setModal(True)
        self.resize(440, 260)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #0c0a06;
                border: 2px solid #ffaa00;
                border-radius: 8px;
            }
            QLabel {
                color: #d8f0ff;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QLineEdit {
                background-color: #14100a;
                border: 1px solid rgba(255, 170, 0, 0.4);
                border-radius: 4px;
                color: #ffffff;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #ffaa00;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("⚠️ PROMOCIÓN A ESTADO CURADO")
        title.setStyleSheet("color: #ffaa00; font-size: 13px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(title)

        desc = QLabel(
            f"Está a punto de promover el plugin '{plugin_id}' a estado CURADO.\n\n"
            "Esta acción permite la ejecución del código sin confinamiento estricto "
            "y quedará registrada permanentemente en el log de auditoría.\n\n"
            "Identidad del revisor (obligatorio):"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #d8c8b0; font-size: 11px;")
        layout.addWidget(desc)

        self.input_reviewed_by = QLineEdit()
        self.input_reviewed_by.setPlaceholderText("ej. auditor@jarvis.security")
        layout.addWidget(self.input_reviewed_by)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ff5c5c; font-size: 11px; font-weight: bold;")
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("CANCELAR")
        self.btn_cancel.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(30, 20, 10, 0.8);
                color: #d8c8b0;
                border: 1px solid rgba(255, 170, 0, 0.3);
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255, 92, 92, 0.2);
                border: 1px solid #ff5c5c;
                color: #ff5c5c;
            }
            """
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_confirm = QPushButton("CONFIRMAR PROMOCIÓN")
        self.btn_confirm.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 170, 0, 0.2);
                color: #ffaa00;
                border: 1px solid #ffaa00;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255, 170, 0, 0.35);
                border: 1px solid #ffcc00;
                color: #ffffff;
            }
            """
        )
        self.btn_confirm.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.btn_confirm)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self) -> None:
        reviewed_by = self.input_reviewed_by.text().strip()
        if not reviewed_by:
            self.lbl_error.setText("El campo de identidad del revisor es obligatorio.")
            self.lbl_error.setVisible(True)
            return
        self.accept()


class PluginManagementDialog(QDialog):
    """
    Diálogo modal que aloja la gestión de plugins: Catálogo Curado y Modo Avanzado.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_status_message: Optional[Callable[[str, bool], None]] = None,
        registry: Optional[PluginRegistry] = None,
        installer: Optional[PluginInstaller] = None,
    ):
        super().__init__(parent)
        self._on_status_message = on_status_message
        self.registry = registry if registry is not None else PluginRegistry()
        self.installer = installer if installer is not None else PluginInstaller(registry=self.registry)
        self._resolved_commit: Optional[str] = None

        self.setWindowTitle("JARVIS — GESTIÓN DE PLUGINS")
        self.setModal(True)
        self.resize(880, 640)
        self.setMinimumSize(820, 560)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #060911;
            }
            QLabel {
                color: #d8f0ff;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            """
        )

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(18, 18, 18, 18)
        self.outer_layout.setSpacing(12)

        # 1. Header con ícono de escudo, títulos y toggle de Modo Avanzado
        header_frame = QFrame(self)
        header_frame.setObjectName("mgmt_header")
        header_frame.setStyleSheet(
            """
            QFrame#mgmt_header {
                background-color: rgba(12, 20, 36, 0.85);
                border: 1px solid rgba(0, 230, 255, 0.25);
                border-radius: 10px;
                padding: 4px;
            }
            """
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)

        icon_label = QLabel("🛡")
        icon_label.setStyleSheet("color: #00e6ff; font-size: 26px;")

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel("GESTIÓN DE PLUGINS")
        title_label.setStyleSheet(
            "color: #00e6ff; font-size: 15px; font-weight: bold; letter-spacing: 1.5px;"
        )
        subtitle_label = QLabel("Catálogo Curado & Confinamiento de Capacidades")
        subtitle_label.setStyleSheet("color: #6e8fa8; font-size: 11px;")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)

        header_layout.addWidget(icon_label)
        header_layout.addSpacing(10)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        # Toggle para Modo Avanzado (spec 4.4) — Ámbar/Rojo
        self.btn_toggle_advanced = QPushButton("MODO AVANZADO ⚠️")
        self.btn_toggle_advanced.setObjectName("btn_toggle_advanced")
        self.btn_toggle_advanced.setCheckable(True)
        self.btn_toggle_advanced.setChecked(False)
        self.btn_toggle_advanced.setStyleSheet(
            """
            QPushButton#btn_toggle_advanced {
                background-color: rgba(40, 25, 10, 0.7);
                color: #ffaa00;
                border: 1px solid rgba(255, 170, 0, 0.5);
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 0.8px;
            }
            QPushButton#btn_toggle_advanced:hover {
                background-color: rgba(255, 170, 0, 0.2);
                border: 1px solid #ffaa00;
            }
            QPushButton#btn_toggle_advanced:checked {
                background-color: rgba(255, 92, 92, 0.25);
                border: 1px solid #ff5c5c;
                color: #ff5c5c;
            }
            """
        )
        self.btn_toggle_advanced.toggled.connect(self._on_advanced_mode_toggled)
        header_layout.addWidget(self.btn_toggle_advanced)
        header_layout.addSpacing(8)

        self.btn_close_top = QPushButton("✕")
        self.btn_close_top.setFixedSize(30, 30)
        self.btn_close_top.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(18, 30, 52, 0.8);
                color: #6e8fa8;
                border: 1px solid rgba(0, 230, 255, 0.2);
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(255, 92, 92, 0.2);
                border: 1px solid #ff5c5c;
                color: #ff5c5c;
            }
            """
        )
        self.btn_close_top.clicked.connect(self.close)
        header_layout.addWidget(self.btn_close_top)

        self.outer_layout.addWidget(header_frame)

        # 2. Vista de Catálogo Curado (visible por defecto)
        self.catalog_screen = PluginCatalogScreen(
            self, on_status_message=on_status_message
        )
        self.outer_layout.addWidget(self.catalog_screen, stretch=1)

        # 3. Vista de Modo Avanzado (spec 4.4 - oculta por defecto, acento ámbar/rojo)
        self.advanced_panel = self._build_advanced_panel()
        self.advanced_panel.setVisible(False)
        self.outer_layout.addWidget(self.advanced_panel, stretch=1)

        # 4. Footer con botón de cierre
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        self.btn_close = QPushButton("CERRAR")
        self.btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(18, 30, 52, 0.9);
                color: #d8f0ff;
                border: 1px solid rgba(0, 230, 255, 0.3);
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 230, 255, 0.18);
                border: 1px solid #00e6ff;
                color: #ffffff;
            }
            """
        )
        self.btn_close.clicked.connect(self.close)
        footer_layout.addWidget(self.btn_close)

        self.outer_layout.addLayout(footer_layout)

    def _build_advanced_panel(self) -> QFrame:
        """
        Construye el panel de Modo Avanzado con borde ámbar/rojo y flujo seguro de instalación.
        """
        panel = QFrame(self)
        panel.setObjectName("advanced_panel")
        panel.setStyleSheet(
            """
            QFrame#advanced_panel {
                background-color: rgba(18, 12, 8, 0.95);
                border: 2px solid rgba(255, 170, 0, 0.7);
                border-radius: 10px;
            }
            QLabel {
                color: #e6dfd5;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QLineEdit {
                background-color: #0d0a06;
                border: 1px solid rgba(255, 170, 0, 0.35);
                border-radius: 6px;
                color: #ffffff;
                padding: 7px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #ffaa00;
            }
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Advertencia superior
        warn_box = QHBoxLayout()
        warn_icon = QLabel("⚠️")
        warn_icon.setStyleSheet("font-size: 20px; color: #ffaa00;")
        warn_text = QLabel(
            "MODO AVANZADO // ZONA DE RIESGO ELEVADO: Instalación directa desde Git.\n"
            "Los plugins fuera del catálogo curado inician como 'no_verificados'. "
            "Debe resolverse el commit SHA-1 antes de autorizar la instalación."
        )
        warn_text.setStyleSheet("color: #ffaa00; font-size: 11px; font-weight: bold;")
        warn_box.addWidget(warn_icon)
        warn_box.addSpacing(6)
        warn_box.addWidget(warn_text, stretch=1)
        layout.addLayout(warn_box)

        # Formulario de entrada
        form_layout = QVBoxLayout()
        form_layout.setSpacing(8)

        lbl_url = QLabel("URL del repositorio Git (HTTPS obligatoria):")
        lbl_url.setStyleSheet("font-size: 11px; font-weight: bold; color: #d8c8b0;")
        self.input_source_url = QLineEdit()
        self.input_source_url.setPlaceholderText("https://github.com/usuario/repositorio.git")
        form_layout.addWidget(lbl_url)
        form_layout.addWidget(self.input_source_url)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        id_box = QVBoxLayout()
        lbl_id = QLabel("ID del Plugin:")
        lbl_id.setStyleSheet("font-size: 11px; font-weight: bold; color: #d8c8b0;")
        self.input_plugin_id = QLineEdit()
        self.input_plugin_id.setPlaceholderText("ej. mi_plugin_personalizado")
        id_box.addWidget(lbl_id)
        id_box.addWidget(self.input_plugin_id)
        meta_row.addLayout(id_box, stretch=1)

        ref_box = QVBoxLayout()
        lbl_ref = QLabel("Referencia Git (rama, tag o commit):")
        lbl_ref.setStyleSheet("font-size: 11px; font-weight: bold; color: #d8c8b0;")
        self.input_ref = QLineEdit("HEAD")
        self.input_ref.setPlaceholderText("HEAD")
        ref_box.addWidget(lbl_ref)
        ref_box.addWidget(self.input_ref)
        meta_row.addLayout(ref_box, stretch=1)

        form_layout.addLayout(meta_row)
        layout.addLayout(form_layout)

        # Mensaje de error / validación en panel
        self.lbl_advanced_error = QLabel("")
        self.lbl_advanced_error.setStyleSheet("color: #ff5c5c; font-size: 11px; font-weight: bold;")
        self.lbl_advanced_error.setVisible(False)
        layout.addWidget(self.lbl_advanced_error)

        # Botón para resolver commit
        resolve_bar = QHBoxLayout()
        self.btn_resolve = QPushButton("1. RESOLVER COMMIT SHA-1")
        self.btn_resolve.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 170, 0, 0.15);
                color: #ffaa00;
                border: 1px solid #ffaa00;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255, 170, 0, 0.3);
                border: 1px solid #ffcc00;
                color: #ffffff;
            }
            """
        )
        self.btn_resolve.clicked.connect(self._on_resolve_clicked)
        resolve_bar.addWidget(self.btn_resolve)
        resolve_bar.addStretch()
        layout.addLayout(resolve_bar)

        # Cuadro de auditoría y resolución de commit
        audit_frame = QFrame()
        audit_frame.setStyleSheet(
            """
            QFrame {
                background-color: #0b0906;
                border: 1px solid rgba(255, 170, 0, 0.3);
                border-radius: 6px;
                padding: 10px;
            }
            """
        )
        audit_layout = QVBoxLayout(audit_frame)
        audit_layout.setSpacing(6)

        commit_title_row = QHBoxLayout()
        lbl_sha_title = QLabel("COMMIT RESUELTO:")
        lbl_sha_title.setStyleSheet("font-size: 10px; color: #9c8a74; font-weight: bold;")
        self.lbl_resolved_commit = QLabel("Ningún commit resuelto")
        self.lbl_resolved_commit.setStyleSheet(
            "font-family: monospace; font-size: 12px; color: #ffaa00; font-weight: bold;"
        )
        commit_title_row.addWidget(lbl_sha_title)
        commit_title_row.addWidget(self.lbl_resolved_commit)
        commit_title_row.addStretch()
        audit_layout.addLayout(commit_title_row)

        status_row = QHBoxLayout()
        lbl_st_title = QLabel("ESTADO EN REGISTRO:")
        lbl_st_title.setStyleSheet("font-size: 10px; color: #9c8a74; font-weight: bold;")
        self.lbl_plugin_status = QLabel("No registrado")
        self.lbl_plugin_status.setStyleSheet("color: #6e8fa8; font-size: 11px; font-weight: bold;")

        self.lbl_active_commit = QLabel("Commit activo: —")
        self.lbl_active_commit.setStyleSheet("color: #9c8a74; font-size: 10px; font-family: monospace;")

        status_row.addWidget(lbl_st_title)
        status_row.addWidget(self.lbl_plugin_status)
        status_row.addSpacing(12)
        status_row.addWidget(self.lbl_active_commit)
        status_row.addStretch()
        audit_layout.addLayout(status_row)

        layout.addWidget(audit_frame)

        # Barra de acciones (Instalar y Promover)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(12)

        self.btn_install_advanced = QPushButton("2. INSTALAR PLUGIN")
        self.btn_install_advanced.setEnabled(False)  # Deshabilitado hasta resolver
        self.btn_install_advanced.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 170, 0, 0.25);
                color: #ffaa00;
                border: 1px solid #ffaa00;
                border-radius: 6px;
                padding: 9px 20px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover:enabled {
                background-color: rgba(255, 170, 0, 0.45);
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: rgba(30, 20, 15, 0.4);
                color: #6e5e4a;
                border: 1px solid rgba(255, 170, 0, 0.15);
            }
            """
        )
        self.btn_install_advanced.clicked.connect(self._on_install_clicked)
        action_bar.addWidget(self.btn_install_advanced)

        self.btn_promote = QPushButton("PROMOVER A CURADO 🛡")
        self.btn_promote.setVisible(False)  # Solo visible si no_verificado
        self.btn_promote.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(0, 230, 128, 0.18);
                color: #00e680;
                border: 1px solid #00e680;
                border-radius: 6px;
                padding: 9px 20px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 230, 128, 0.35);
                color: #ffffff;
            }
            """
        )
        self.btn_promote.clicked.connect(self._on_promote_clicked)
        action_bar.addWidget(self.btn_promote)

        action_bar.addStretch()
        layout.addLayout(action_bar)
        layout.addStretch()

        return panel

    def _on_advanced_mode_toggled(self, checked: bool) -> None:
        """Alterna entre el catálogo curado y el panel de Modo Avanzado."""
        if checked:
            self.catalog_screen.setVisible(False)
            self.advanced_panel.setVisible(True)
            self.btn_toggle_advanced.setText("← VOLVER AL CATÁLOGO")
        else:
            self.advanced_panel.setVisible(False)
            self.catalog_screen.setVisible(True)
            self.btn_toggle_advanced.setText("MODO AVANZADO ⚠️")

    def _on_resolve_clicked(self) -> None:
        """
        Resuelve la referencia Git a un commit SHA-1 verificando la URL
        mediante allowlist estricta antes de invocar cualquier subproceso git.
        """
        url = self.input_source_url.text().strip()
        ref = self.input_ref.text().strip() or "HEAD"
        self.lbl_advanced_error.setVisible(False)
        self.lbl_advanced_error.setText("")

        # 1. Validación en UI antes de tocar subprocess/git
        try:
            validate_source_url(url)
        except (ValueError, Exception) as e:
            err_msg = str(e)
            self.lbl_advanced_error.setText(f"URL no permitida: {err_msg}")
            self.lbl_advanced_error.setVisible(True)
            self.btn_install_advanced.setEnabled(False)
            self.lbl_resolved_commit.setText("Ningún commit resuelto")
            if self._on_status_message:
                self._on_status_message(f"URL rechazada por seguridad: {err_msg}", False)
            return

        # 2. Resolución del commit SHA-1
        try:
            commit_sha = resolve_git_ref(source_url=url, ref=ref)
            self._resolved_commit = commit_sha
            self.lbl_resolved_commit.setText(commit_sha)
            self.btn_install_advanced.setEnabled(True)

            # Si el plugin_id está vacío, inferirlo del repo
            plugin_id = self.input_plugin_id.text().strip()
            if not plugin_id:
                inferred = url.rstrip("/").split("/")[-1]
                if inferred.endswith(".git"):
                    inferred = inferred[:-4]
                self.input_plugin_id.setText(inferred)
                plugin_id = inferred

            self._update_plugin_status_display(plugin_id)

        except Exception as e:
            err_msg = str(e)
            self.lbl_advanced_error.setText(f"Error al resolver referencia: {err_msg}")
            self.lbl_advanced_error.setVisible(True)
            self.btn_install_advanced.setEnabled(False)
            self.lbl_resolved_commit.setText("Error en resolución")
            if self._on_status_message:
                self._on_status_message(f"Fallo al resolver {url}@{ref}: {err_msg}", False)

    def _update_plugin_status_display(self, plugin_id: str) -> None:
        """Actualiza las etiquetas y la visibilidad del botón de promoción."""
        if not plugin_id:
            self.lbl_plugin_status.setText("No especificado")
            self.lbl_plugin_status.setStyleSheet("color: #6e8fa8; font-weight: bold;")
            self.lbl_active_commit.setText("Commit activo: —")
            self.btn_promote.setVisible(False)
            return

        plugin_data = self.registry.get_plugin(plugin_id)
        if not plugin_data:
            self.lbl_plugin_status.setText("No instalado")
            self.lbl_plugin_status.setStyleSheet("color: #6e8fa8; font-weight: bold;")
            self.lbl_active_commit.setText("Commit activo: —")
            self.btn_promote.setVisible(False)
        else:
            status = plugin_data.get("status", "no_verificado")
            active_hash = plugin_data.get("active_commit_hash", "—")
            self.lbl_active_commit.setText(f"Commit activo: {active_hash}")

            if status == "curado":
                self.lbl_plugin_status.setText("CURADO")
                self.lbl_plugin_status.setStyleSheet(
                    "background-color: rgba(0, 230, 128, 0.2); color: #00e680; "
                    "border: 1px solid #00e680; border-radius: 4px; padding: 2px 8px; font-weight: bold;"
                )
                self.btn_promote.setVisible(False)
            else:
                self.lbl_plugin_status.setText("NO VERIFICADO")
                self.lbl_plugin_status.setStyleSheet(
                    "background-color: rgba(255, 170, 0, 0.2); color: #ffaa00; "
                    "border: 1px solid #ffaa00; border-radius: 4px; padding: 2px 8px; font-weight: bold;"
                )
                self.btn_promote.setVisible(True)

    def _on_install_clicked(self) -> None:
        """Instala el plugin desde URL tras verificar que fue resuelto."""
        if not self._resolved_commit:
            self.lbl_advanced_error.setText("Debe resolver el commit antes de instalar.")
            self.lbl_advanced_error.setVisible(True)
            return

        url = self.input_source_url.text().strip()
        plugin_id = self.input_plugin_id.text().strip()
        ref = self.input_ref.text().strip() or "HEAD"

        if not plugin_id:
            self.lbl_advanced_error.setText("El campo 'ID del Plugin' es obligatorio.")
            self.lbl_advanced_error.setVisible(True)
            return

        try:
            self.installer.install_from_url(
                source_url=url,
                plugin_id=plugin_id,
                ref=ref,
            )
            msg = f"Plugin '{plugin_id}' instalado correctamente desde {url}."
            if self._on_status_message:
                self._on_status_message(msg, True)
            self._update_plugin_status_display(plugin_id)
            self.catalog_screen.refresh()
        except Exception as e:
            err_msg = f"Error al instalar plugin '{plugin_id}': {e}"
            self.lbl_advanced_error.setText(err_msg)
            self.lbl_advanced_error.setVisible(True)
            if self._on_status_message:
                self._on_status_message(err_msg, False)

    def _on_promote_clicked(self) -> None:
        """Abre el diálogo modal de confirmación con campo obligatorio reviewed_by."""
        plugin_id = self.input_plugin_id.text().strip()
        if not plugin_id:
            self.lbl_advanced_error.setText("No hay un plugin válido para promover.")
            self.lbl_advanced_error.setVisible(True)
            return

        dialog = PromoteCuratedDialog(self, plugin_id=plugin_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            reviewed_by = dialog.input_reviewed_by.text().strip()
            if not reviewed_by:
                return  # Salvaguarda

            success = self.registry.promote_to_curated(
                plugin_id=plugin_id,
                reviewed_by=reviewed_by,
            )
            if success:
                msg = f"Plugin '{plugin_id}' promovido a CURADO por {reviewed_by}."
                if self._on_status_message:
                    self._on_status_message(msg, True)
                self._update_plugin_status_display(plugin_id)
                self.catalog_screen.refresh()
            else:
                msg = f"No se pudo promover el plugin '{plugin_id}' en el registro."
                if self._on_status_message:
                    self._on_status_message(msg, False)

    @classmethod
    def open_management(
        cls,
        parent: Optional[QWidget] = None,
        on_status_message: Optional[Callable[[str, bool], None]] = None,
        registry: Optional[PluginRegistry] = None,
        installer: Optional[PluginInstaller] = None,
    ) -> "PluginManagementDialog":
        """
        Instancia el diálogo, refresca el catálogo y lo ejecuta de forma modal.
        """
        dialog = cls(
            parent=parent,
            on_status_message=on_status_message,
            registry=registry,
            installer=installer,
        )
        dialog.catalog_screen.refresh()
        dialog.exec()
        return dialog
