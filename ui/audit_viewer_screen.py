"""
Pantalla de Solo Lectura para Inspección de Auditoría (Audit Logs) para JARVIS.
Carga y visualiza los registros inmutables persistidos por core/audit_log.py.

Requisitos de auditoría y diseño:
- Widget embebible de solo lectura (QTableWidget con EditTrigger.NoEditTriggers).
- Columnas: Timestamp, Plugin ID, Acción, Resultado y botón de detalles completos.
- Enmascarado estricto de valores sensibles: cualquier clave que contenga 'key',
  'token', 'password', 'secret' (case-insensitive) se muestra como '***'.
- Paginación mediante LIMIT/OFFSET ("Cargar más") y botón "Actualizar".
- Filtros client-side por plugin_id y por resultado sin perder los datos ya cargados.
- Ausencia total de controles o métodos de escritura/borrado (solo lectura garantizada).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.audit_log import AuditLogger, get_default_audit_logger


SENSITIVE_KEY_SUBSTRINGS = ("key", "token", "password", "secret")


def mask_sensitive_data(data: Any) -> Any:
    """
    Enmascara recursivamente cualquier valor cuya clave contenga
    'key', 'token', 'password' o 'secret' (case-insensitive), reemplazándolo por '***'.
    Soporta dicts, lists y strings JSON.
    """
    if isinstance(data, dict):
        masked_dict = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                masked_dict[k] = "***"
            else:
                masked_dict[k] = mask_sensitive_data(v)
        return masked_dict
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        # Si es un string que contiene JSON, decodificar, enmascarar y re-codificar
        try:
            parsed = json.loads(data)
            if isinstance(parsed, (dict, list)):
                return mask_sensitive_data(parsed)
        except (ValueError, TypeError):
            pass
        return data
    return data


class AuditDetailsDialog(QDialog):
    """
    Diálogo modal de solo lectura para examinar los detalles completos de un evento de auditoría
    con todos los campos sensibles debidamente enmascarados.
    """

    def __init__(self, parent: Optional[QWidget], record: Dict[str, Any]):
        super().__init__(parent)
        self.setWindowTitle(f"DETALLES DE AUDITORÍA — REGISTRO #{record.get('id', 'N/A')}")
        self.setModal(True)
        self.resize(600, 480)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #060911;
                border: 1px solid rgba(0, 230, 255, 0.3);
                border-radius: 8px;
            }
            QLabel {
                color: #d8f0ff;
                font-family: 'Segoe UI', sans-serif;
            }
            QTextEdit {
                background-color: #0c101c;
                color: #00e6ff;
                border: 1px solid rgba(0, 230, 255, 0.2);
                border-radius: 6px;
                font-family: monospace;
                font-size: 11px;
                padding: 8px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel(f"EVENTO DE AUDITORÍA // {record.get('action', 'ACCIÓN DESCONOCIDA')}")
        title.setStyleSheet("color: #00e6ff; font-size: 13px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(title)

        # Metadatos del registro
        meta_box = QFrame(self)
        meta_box.setStyleSheet(
            """
            QFrame {
                background-color: rgba(12, 20, 36, 0.7);
                border: 1px solid rgba(0, 230, 255, 0.15);
                border-radius: 6px;
                padding: 6px;
            }
            """
        )
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.setSpacing(4)

        ts_lbl = QLabel(f"<b>Timestamp:</b> {record.get('timestamp', '—')}")
        plugin_lbl = QLabel(f"<b>Plugin ID:</b> {record.get('plugin_id', '—')}")
        cap_lbl = QLabel(f"<b>Capacidad:</b> {record.get('capability', '—')}")
        res_lbl = QLabel(f"<b>Resultado:</b> {record.get('result_status', '—')} (Allowed: {bool(record.get('allowed', 0))})")
        reason_lbl = QLabel(f"<b>Motivo / Causa:</b> {record.get('reason', '—') or '—'}")

        for lbl in (ts_lbl, plugin_lbl, cap_lbl, res_lbl, reason_lbl):
            lbl.setStyleSheet("font-size: 11px; color: #9cb8d0;")
            meta_layout.addWidget(lbl)

        layout.addWidget(meta_box)

        # Detalles enmascarados
        layout.addWidget(QLabel("Detalles de Invocación (Campos sensibles enmascarados con '***'):"))

        raw_details = record.get("details")
        masked_details = mask_sensitive_data(raw_details)

        if isinstance(masked_details, (dict, list)):
            display_text = json.dumps(masked_details, indent=2, ensure_ascii=False)
        else:
            display_text = str(masked_details) if masked_details is not None else "Sin detalles registrados."

        self.txt_details = QTextEdit()
        self.txt_details.setReadOnly(True)
        self.txt_details.setPlainText(display_text)
        layout.addWidget(self.txt_details, stretch=1)

        # Botón de cierre
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_close = QPushButton("CERRAR")
        btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(18, 30, 52, 0.9);
                color: #d8f0ff;
                border: 1px solid rgba(0, 230, 255, 0.3);
                border-radius: 6px;
                padding: 6px 20px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 230, 255, 0.2);
                border: 1px solid #00e6ff;
            }
            """
        )
        btn_close.clicked.connect(self.close)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)


class AuditViewerScreen(QWidget):
    """
    Widget embebible de visualización de registros de auditoría (solo lectura).
    """

    PAGE_SIZE = 50

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        super().__init__(parent)
        self.audit_logger = audit_logger if audit_logger is not None else get_default_audit_logger()
        self._loaded_logs: List[Dict[str, Any]] = []
        self._current_offset: int = 0

        self._setup_ui()
        self.refresh_logs()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. Barra de Filtros y Acciones
        filter_frame = QFrame(self)
        filter_frame.setStyleSheet(
            """
            QFrame {
                background-color: rgba(12, 20, 36, 0.85);
                border: 1px solid rgba(0, 230, 255, 0.2);
                border-radius: 8px;
            }
            QLabel {
                color: #9cb8d0;
                font-size: 11px;
                font-weight: bold;
            }
            QComboBox {
                background-color: #090e1a;
                color: #d8f0ff;
                border: 1px solid rgba(0, 230, 255, 0.3);
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                min-width: 140px;
            }
            QComboBox:hover {
                border: 1px solid #00e6ff;
            }
            QComboBox QAbstractItemView {
                background-color: #090e1a;
                color: #d8f0ff;
                selection-background-color: rgba(0, 230, 255, 0.3);
            }
            """
        )
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(12)

        # Filtro Plugin ID
        filter_layout.addWidget(QLabel("Plugin:"))
        self.combo_plugin_id = QComboBox()
        self.combo_plugin_id.addItem("Todos los plugins", userData="ALL")
        self.combo_plugin_id.currentIndexChanged.connect(self._apply_client_filters)
        filter_layout.addWidget(self.combo_plugin_id)

        # Filtro Resultado
        filter_layout.addWidget(QLabel("Resultado:"))
        self.combo_result = QComboBox()
        self.combo_result.addItem("Todos los resultados", userData="ALL")
        self.combo_result.addItem("éxito", userData="éxito")
        self.combo_result.addItem("denegado", userData="denegado")
        self.combo_result.addItem("rate_limit", userData="rate_limit")
        self.combo_result.addItem("error", userData="error")
        self.combo_result.currentIndexChanged.connect(self._apply_client_filters)
        filter_layout.addWidget(self.combo_result)

        filter_layout.addStretch()

        # Botón Actualizar
        self.btn_refresh = QPushButton("ACTUALIZAR 🔄")
        self.btn_refresh.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(18, 30, 52, 0.9);
                color: #00e6ff;
                border: 1px solid rgba(0, 230, 255, 0.35);
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 230, 255, 0.2);
                border: 1px solid #00e6ff;
            }
            """
        )
        self.btn_refresh.clicked.connect(self.refresh_logs)
        filter_layout.addWidget(self.btn_refresh)

        layout.addWidget(filter_frame)

        # 2. Tabla de Auditoría (Solo Lectura)
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Timestamp", "Plugin ID", "Acción", "Resultado", "Detalles"
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #060911;
                alternate-background-color: #0a0f1d;
                color: #d8f0ff;
                gridline-color: rgba(0, 230, 255, 0.1);
                border: 1px solid rgba(0, 230, 255, 0.2);
                border-radius: 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background-color: rgba(0, 230, 255, 0.25);
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0e1526;
                color: #00e6ff;
                padding: 6px;
                border: 1px solid rgba(0, 230, 255, 0.15);
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 0.5px;
            }
            """
        )
        layout.addWidget(self.table, stretch=1)

        # 3. Footer con Botón "Cargar Más" y Contador
        footer_layout = QHBoxLayout()
        self.lbl_record_count = QLabel("0 registros cargados")
        self.lbl_record_count.setStyleSheet("color: #6e8fa8; font-size: 11px;")
        footer_layout.addWidget(self.lbl_record_count)

        footer_layout.addStretch()

        self.btn_load_more = QPushButton("CARGAR MÁS REGISTROS ⬇")
        self.btn_load_more.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(18, 30, 52, 0.85);
                color: #d8f0ff;
                border: 1px solid rgba(0, 230, 255, 0.3);
                border-radius: 6px;
                padding: 6px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover:enabled {
                background-color: rgba(0, 230, 255, 0.18);
                border: 1px solid #00e6ff;
                color: #ffffff;
            }
            QPushButton:disabled {
                color: #4a5d6e;
                border: 1px solid rgba(0, 230, 255, 0.1);
            }
            """
        )
        self.btn_load_more.clicked.connect(self.load_more_logs)
        footer_layout.addWidget(self.btn_load_more)

        layout.addLayout(footer_layout)

    def refresh_logs(self) -> None:
        """Reinicia la consulta desde el inicio y recarga el primer lote de registros."""
        self._current_offset = 0
        try:
            logs = self.audit_logger.query_logs(limit=self.PAGE_SIZE, offset=0)
        except TypeError:
            # En caso de que la implementación no reciba offset
            logs = self.audit_logger.query_logs(limit=self.PAGE_SIZE)

        self._loaded_logs = list(logs)
        self._current_offset = len(self._loaded_logs)

        # Actualizar lista de plugins en el filtro
        self._update_plugin_filter_options()
        self._apply_client_filters()

        self.btn_load_more.setEnabled(len(logs) == self.PAGE_SIZE)

    def load_more_logs(self) -> None:
        """Paginación incremental mediante LIMIT y OFFSET."""
        try:
            more_logs = self.audit_logger.query_logs(
                limit=self.PAGE_SIZE,
                offset=self._current_offset,
            )
        except TypeError:
            more_logs = []

        if more_logs:
            self._loaded_logs.extend(more_logs)
            self._current_offset += len(more_logs)
            self._update_plugin_filter_options()
            self._apply_client_filters()

            if len(more_logs) < self.PAGE_SIZE:
                self.btn_load_more.setEnabled(False)
        else:
            self.btn_load_more.setEnabled(False)

    def _update_plugin_filter_options(self) -> None:
        """Agrega dinámicamente nuevos plugin_id encontrados sin perder la selección actual."""
        current_selection = self.combo_plugin_id.currentData()

        known_plugins = sorted({
            str(r.get("plugin_id")) for r in self._loaded_logs if r.get("plugin_id")
        })

        self.combo_plugin_id.blockSignals(True)
        self.combo_plugin_id.clear()
        self.combo_plugin_id.addItem("Todos los plugins", userData="ALL")
        for pid in known_plugins:
            self.combo_plugin_id.addItem(pid, userData=pid)

        # Restaurar selección si aún existe
        idx = self.combo_plugin_id.findData(current_selection)
        if idx >= 0:
            self.combo_plugin_id.setCurrentIndex(idx)
        else:
            self.combo_plugin_id.setCurrentIndex(0)
        self.combo_plugin_id.blockSignals(False)

    def _apply_client_filters(self) -> None:
        """
        Aplica los filtros de plugin_id y resultado sobre self._loaded_logs (client-side)
        sin perder los registros originales cargados.
        """
        sel_plugin = self.combo_plugin_id.currentData() or "ALL"
        sel_result = self.combo_result.currentData() or "ALL"

        filtered_records = []
        for r in self._loaded_logs:
            # Filtro por plugin_id
            if sel_plugin != "ALL" and str(r.get("plugin_id")) != str(sel_plugin):
                continue

            # Filtro por resultado
            if sel_result != "ALL":
                r_status = str(r.get("result_status", "")).lower()
                target_status = str(sel_result).lower()
                if target_status not in r_status:
                    continue

            filtered_records.append(r)

        self._populate_table(filtered_records)
        self.lbl_record_count.setText(
            f"Mostrando {len(filtered_records)} de {len(self._loaded_logs)} registros cargados"
        )

    def _populate_table(self, records: List[Dict[str, Any]]) -> None:
        """Rellena las celdas de la tabla con los registros proporcionados."""
        self.table.setRowCount(len(records))

        for row_idx, r in enumerate(records):
            # 1. Timestamp
            item_ts = QTableWidgetItem(str(r.get("timestamp", "")))
            item_ts.setForeground(Qt.GlobalColor.white)
            self.table.setItem(row_idx, 0, item_ts)

            # 2. Plugin ID
            item_pid = QTableWidgetItem(str(r.get("plugin_id", "")))
            item_pid.setForeground(Qt.GlobalColor.cyan)
            self.table.setItem(row_idx, 1, item_pid)

            # 3. Acción
            item_act = QTableWidgetItem(str(r.get("action", "")))
            item_act.setForeground(Qt.GlobalColor.white)
            self.table.setItem(row_idx, 2, item_act)

            # 4. Resultado (estilizado con color según estado)
            res_str = str(r.get("result_status", ""))
            item_res = QTableWidgetItem(res_str)
            item_res.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            res_lower = res_str.lower()
            if "éxito" in res_lower or "allow" in res_lower:
                item_res.setForeground(Qt.GlobalColor.green)
            elif "denegado" in res_lower:
                item_res.setForeground(Qt.GlobalColor.red)
            elif "rate_limit" in res_lower:
                item_res.setForeground(Qt.GlobalColor.yellow)
            else:
                item_res.setForeground(Qt.GlobalColor.red)

            self.table.setItem(row_idx, 3, item_res)

            # 5. Botón Ver Detalles
            btn_details = QPushButton("Ver detalles 🔍")
            btn_details.setStyleSheet(
                """
                QPushButton {
                    background-color: rgba(0, 230, 255, 0.15);
                    color: #00e6ff;
                    border: 1px solid rgba(0, 230, 255, 0.4);
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(0, 230, 255, 0.3);
                    color: #ffffff;
                }
                """
            )
            # Conexión con captura de record
            btn_details.clicked.connect(lambda _, rec=r: self._show_details(rec))
            self.table.setCellWidget(row_idx, 4, btn_details)

    def _show_details(self, record: Dict[str, Any]) -> None:
        """Abre el diálogo modal de inspección de detalles con valores sensibles enmascarados."""
        dlg = AuditDetailsDialog(self, record=record)
        dlg.exec()


class AuditViewerDialog(QDialog):
    """
    Diálogo modal de solo lectura para inspección de los registros de auditoría.
    Aloja una instancia de AuditViewerScreen.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("JARVIS — REGISTRO DE AUDITORÍA")
        self.setModal(True)
        self.resize(920, 600)
        self.setMinimumSize(800, 500)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.setStyleSheet("QDialog { background-color: #060911; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header con título y botón de cierre
        header_layout = QHBoxLayout()
        title_label = QLabel("REGISTRO DE AUDITORÍA // HISTÓRICO DE DISPATCHER")
        title_label.setStyleSheet(
            "color: #00e6ff; font-size: 14px; font-weight: bold; letter-spacing: 1px;"
        )
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        btn_close_top = QPushButton("✕")
        btn_close_top.setFixedSize(28, 28)
        btn_close_top.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(18, 30, 52, 0.8);
                color: #6e8fa8;
                border: 1px solid rgba(0, 230, 255, 0.2);
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 92, 92, 0.2);
                border: 1px solid #ff5c5c;
                color: #ff5c5c;
            }
            """
        )
        btn_close_top.clicked.connect(self.close)
        header_layout.addWidget(btn_close_top)
        layout.addLayout(header_layout)

        # Pantalla de visualización embebida
        self.screen = AuditViewerScreen(self, audit_logger=audit_logger)
        layout.addWidget(self.screen, stretch=1)

    @classmethod
    def open_viewer(
        cls,
        parent: Optional[QWidget] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> "AuditViewerDialog":
        dialog = cls(parent=parent, audit_logger=audit_logger)
        dialog.screen.refresh_logs()
        dialog.exec()
        return dialog
