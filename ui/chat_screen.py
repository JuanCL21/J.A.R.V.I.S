"""
Pantalla de Chat Simple / Operativo para JARVIS.
Adaptada fielmente al diseño de Stitch: 'JARVIS - Chat Simple' (ID: f78fa935c34d4c5baf3dd4878536964e).

Características:
- Barra lateral de sesiones/conversaciones (280px) con botón '+ Nueva conversación',
  filtro de búsqueda en historial, lista agrupada por fechas y tarjeta de 'Modo local seguro'.
- Columna central con topbar de sesión ('Auditoría de ventas Q3', status 'JARVIS está listo',
  botones 'Reiniciar chat', 'Exportar' y toggle de sidecar).
- Stream de mensajes centrado (max-w 768px):
  - Badge sutil 'Procesado de forma 100% privada y local'.
  - Burbujas de usuario con chips de adjuntos verificados.
  - Respuestas de JARVIS con bloques de código destacados (copiar / ejecutar),
    tarjetas de resumen de resultados, vista rápida de artefactos y barra de acciones (copiar, escuchar, regenerar, feedback).
- Composer inferior espacioso con botones de adjunto, voz y envío.
- Panel lateral de telemetría/consola de eventos (sidecar) integrado y toggleable.
"""

from __future__ import annotations

import datetime
from typing import Callable, List, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Colors, Radius, Spacing, Typography


# ==============================================================================
# Tarjeta de Sesión en la Barra Lateral
# ==============================================================================
class SessionThreadItem(QFrame):
    """
    Elemento individual de la lista de conversaciones.
    """

    clicked = pyqtSignal(str)

    def __init__(
        self,
        thread_id: str,
        title: str,
        subtitle: str,
        time_ago: str,
        icon: str = "💬",
        is_active: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.thread_id = thread_id
        self._is_active = is_active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setSpacing(10)

        # Ícono en caja redondeada
        self.icon_box = QLabel(icon)
        self.icon_box.setFixedSize(34, 34)
        self.icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_box)

        # Título y Subtítulo
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 600;")
        text_col.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_LOW};")
        text_col.addWidget(self.lbl_subtitle)

        layout.addLayout(text_col, stretch=1)

        # Tiempo relativo
        self.lbl_time = QLabel(time_ago)
        self.lbl_time.setStyleSheet(f"font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        layout.addWidget(self.lbl_time)

        self.set_active(is_active)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        if active:
            self.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_2};
                    border: 1px solid {Colors.PRIMARY}44;
                    border-left: 3px solid {Colors.PRIMARY};
                    border-radius: {Radius.MD}px;
                }}
                """
            )
            self.icon_box.setStyleSheet(
                f"background-color: {Colors.PRIMARY}22; color: {Colors.PRIMARY_BRIGHT}; "
                f"font-size: 14px; border-radius: {Radius.SM}px;"
            )
            self.lbl_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {Colors.TEXT_HIGH};")
            self.lbl_time.setStyleSheet(f"font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; color: {Colors.SECONDARY};")
        else:
            self.setStyleSheet(
                f"""
                QFrame {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: {Radius.MD}px;
                }}
                QFrame:hover {{
                    background-color: {Colors.SURFACE_1};
                }}
                """
            )
            self.icon_box.setStyleSheet(
                f"background-color: {Colors.SURFACE_2}; color: {Colors.TEXT_LOW}; "
                f"font-size: 14px; border-radius: {Radius.SM}px;"
            )
            self.lbl_title.setStyleSheet(f"font-size: 13px; font-weight: 500; color: {Colors.TEXT_MEDIUM};")
            self.lbl_time.setStyleSheet(f"font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; color: {Colors.TEXT_LOW};")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.thread_id)
        super().mousePressEvent(event)


# ==============================================================================
# Bloque de Código Estilizado con Acciones
# ==============================================================================
class StitchCodeBlock(QFrame):
    """
    Bloque de código con cabecera técnica, badge 'Verificado' y botones Copiar/Ejecutar.
    """

    def __init__(
        self,
        title: str,
        code: str,
        language: str = "python",
        on_run: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._code = code
        self._on_run = on_run

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_LOWEST};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header Bar
        header = QFrame()
        header.setFixedHeight(34)
        header.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_2};
                border-bottom: 1px solid {Colors.BORDER_STRUCTURAL};
                border-top-left-radius: {Radius.MD}px;
                border-top-right-radius: {Radius.MD}px;
            }}
            """
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 12, 0)
        h_layout.setSpacing(8)

        lbl_icon = QLabel("❮❯")
        lbl_icon.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 11px; font-weight: bold;")
        h_layout.addWidget(lbl_icon)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {Colors.TEXT_MEDIUM}; font-size: 11px; font-weight: 600;")
        h_layout.addWidget(lbl_title)

        badge_verif = QLabel("✓ Verificado")
        badge_verif.setStyleSheet(
            f"background-color: {Colors.SECONDARY}22; color: {Colors.SECONDARY}; "
            f"font-size: 10px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"padding: 2px 6px; border-radius: {Radius.XS}px;"
        )
        h_layout.addWidget(badge_verif)
        h_layout.addStretch()

        btn_copy = QPushButton("📋 Copiar")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_MEDIUM};
                font-size: 11px;
                font-weight: 500;
                padding: 2px 6px;
            }}
            QPushButton:hover {{
                color: {Colors.PRIMARY_BRIGHT};
            }}
            """
        )
        btn_copy.clicked.connect(self._copy_code)
        h_layout.addWidget(btn_copy)

        if on_run is not None:
            btn_run = QPushButton("▶ Ejecutar")
            btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_run.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {Colors.SECONDARY};
                    font-size: 11px;
                    font-weight: 600;
                    padding: 2px 6px;
                }}
                QPushButton:hover {{
                    color: {Colors.SECONDARY_HOVER};
                }}
                """
            )
            btn_run.clicked.connect(lambda: self._on_run(self._code))
            h_layout.addWidget(btn_run)

        layout.addWidget(header)

        # Code Body
        code_box = QTextEdit()
        code_box.setReadOnly(True)
        code_box.setPlainText(code)
        code_box.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                color: {Colors.TEXT_HIGH};
                font-family: '{Typography.FONT_FAMILY_MONO}';
                font-size: 11.5px;
                line-height: 1.4;
                padding: 10px;
            }}
            """
        )
        # Ajustar altura según cantidad de líneas
        lines = max(2, min(14, code.count("\n") + 1))
        code_box.setFixedHeight(lines * 20 + 20)
        layout.addWidget(code_box)

    def _copy_code(self) -> None:
        from PyQt6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._code)


# ==============================================================================
# Gráfico de Tendencia Vectorial (Stitch SVG Preview)
# ==============================================================================
class TrendChartWidget(QWidget):
    """
    Gráfico de tendencia vectorial idéntico a Stitch:
    Curva de Ingresos Diarios (Q3) con área de gradiente cian, línea de umbral P95 punteada y punto destacado.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(95)
        self.setMinimumWidth(240)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        scale_x = w / 300.0
        scale_y = h / 90.0

        path = QPainterPath()
        path.moveTo(0 * scale_x, 75 * scale_y)
        path.quadTo(30 * scale_x, 60 * scale_y, 60 * scale_x, 70 * scale_y)
        path.quadTo(90 * scale_x, 80 * scale_y, 120 * scale_x, 40 * scale_y)
        path.quadTo(150 * scale_x, 0 * scale_y, 180 * scale_x, 50 * scale_y)
        path.quadTo(210 * scale_x, 100 * scale_y, 240 * scale_x, 25 * scale_y)
        path.quadTo(270 * scale_x, -10 * scale_y, 300 * scale_x, 15 * scale_y)

        # Gradiente de relleno hacia la base
        fill_path = QPainterPath(path)
        fill_path.lineTo(300 * scale_x, h)
        fill_path.lineTo(0, h)
        fill_path.closeSubpath()

        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(56, 189, 248, 70))
        grad.setColorAt(1.0, QColor(56, 189, 248, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawPath(fill_path)

        # Trazo de la curva cian
        pen_curve = QPen(QColor(Colors.PRIMARY_BRIGHT), 2.0)
        painter.setPen(pen_curve)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Línea de umbral P95 ($14.8k) punteada
        threshold_y = 25 * scale_y
        pen_dash = QPen(QColor(Colors.SECONDARY), 1.2, Qt.PenStyle.DashLine)
        pen_dash.setDashPattern([3, 3])
        painter.setPen(pen_dash)
        painter.drawLine(0, int(threshold_y), int(w), int(threshold_y))

        # Punto destacado en (240, 25)
        dot_x = 240 * scale_x
        dot_y = 25 * scale_y
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Colors.SECONDARY))
        painter.drawEllipse(QPointF(dot_x, dot_y), 4.0, 4.0)

        painter.end()


# ==============================================================================
# Tarjeta de Mensaje de Chat (Usuario y Asistente Stitch)
# ==============================================================================
class StitchChatMessageCard(QFrame):
    """
    Tarjeta de mensaje en el stream de chat con el diseño exacto de Stitch:
    - Header con remitente, hora y status (e.g. 'Tú • 14:31' o '● JARVIS • 14:31 • 🔒 Protegido')
    - Contenedor con texto enriquecido
    - Chips de adjunto o bloques de código
    - Tarjeta de resumen de análisis y preview visual (TrendChart + Artifacts)
    - Barra de acciones (Copiar, Escuchar, etc.)
    """

    def __init__(
        self,
        sender: str,
        text: str,
        is_user: bool = False,
        attachment_name: Optional[str] = None,
        attachment_info: Optional[str] = None,
        code_snippet: Optional[str] = None,
        has_preview: bool = False,
        on_tts_speak: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.sender = sender
        self.text = text
        self.is_user = is_user
        self._on_tts_speak = on_tts_speak

        now_str = datetime.datetime.now().strftime("%H:%M")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Meta Header
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        if is_user:
            meta_row.addStretch()
            lbl_sender = QLabel("Tú")
            lbl_sender.setStyleSheet(f"color: {Colors.PRIMARY_BRIGHT}; font-size: 11px; font-weight: 700;")
            lbl_dot = QLabel("•")
            lbl_dot.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px;")
            lbl_time = QLabel(now_str)
            lbl_time.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            meta_row.addWidget(lbl_sender)
            meta_row.addWidget(lbl_dot)
            meta_row.addWidget(lbl_time)
        else:
            lbl_dot_green = QLabel("●")
            lbl_dot_green.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px;")
            lbl_sender = QLabel("JARVIS")
            lbl_sender.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 11px; font-weight: 700;")
            lbl_dot = QLabel("•")
            lbl_dot.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px;")
            lbl_time = QLabel(now_str)
            lbl_time.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            lbl_protected = QLabel("🔒 Protegido")
            lbl_protected.setToolTip("Ejecución en sandbox local con aislamiento seguro")
            lbl_protected.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px; margin-left: 6px;")

            meta_row.addWidget(lbl_dot_green)
            meta_row.addWidget(lbl_sender)
            meta_row.addWidget(lbl_dot)
            meta_row.addWidget(lbl_time)
            meta_row.addWidget(lbl_protected)
            meta_row.addStretch()

        main_layout.addLayout(meta_row)

        # Bubble Container
        bubble_box = QFrame()
        b_layout = QVBoxLayout(bubble_box)
        b_layout.setContentsMargins(16, 14, 16, 14)
        b_layout.setSpacing(12)

        if is_user:
            bubble_box.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_2};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.LG}px;
                }}
                """
            )
        else:
            bubble_box.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_1};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.LG}px;
                }}
                """
            )

        # Message Text
        lbl_text = QLabel(text)
        lbl_text.setWordWrap(True)
        lbl_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_text.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 13.5px; line-height: 1.5;")
        b_layout.addWidget(lbl_text)

        # Chip de archivo adjunto (si aplica)
        if attachment_name:
            attach_chip = QFrame()
            attach_chip.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_LOWEST};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.MD}px;
                    padding: 6px;
                }}
                """
            )
            ac_layout = QHBoxLayout(attach_chip)
            ac_layout.setContentsMargins(10, 6, 10, 6)
            ac_layout.setSpacing(8)

            ic_file = QLabel("📊")
            ic_file.setStyleSheet("font-size: 16px;")
            ac_layout.addWidget(ic_file)

            f_col = QVBoxLayout()
            f_col.setContentsMargins(0, 0, 0, 0)
            f_col.setSpacing(1)
            lbl_fn = QLabel(attachment_name)
            lbl_fn.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {Colors.TEXT_HIGH};")
            f_col.addWidget(lbl_fn)
            lbl_fi = QLabel(attachment_info or "Verificado en enclave")
            lbl_fi.setStyleSheet(f"font-size: 10px; color: {Colors.TEXT_LOW};")
            f_col.addWidget(lbl_fi)
            ac_layout.addLayout(f_col, stretch=1)

            lbl_v = QLabel("✓ Verificado")
            lbl_v.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 11px; font-weight: 600;")
            ac_layout.addWidget(lbl_v)

            b_layout.addWidget(attach_chip)

        # Bloque de código (si aplica)
        if code_snippet:
            code_widget = StitchCodeBlock("Transformación de datos", code_snippet)
            b_layout.addWidget(code_widget)

        # Preview Visual y Resumen de Resultados (Fiel a Stitch 4_chat_code.html)
        if has_preview:
            # 1. Resultados del análisis
            res_frame = QFrame()
            res_frame.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_CONTAINER};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.MD}px;
                    padding: 4px;
                }}
                """
            )
            res_layout = QVBoxLayout(res_frame)
            res_layout.setContentsMargins(10, 8, 10, 8)
            res_layout.setSpacing(6)

            hdr_res = QHBoxLayout()
            hdr_res.setSpacing(6)
            ic_chk = QLabel("✓")
            ic_chk.setStyleSheet(f"color: {Colors.SECONDARY}; font-weight: bold; font-size: 12px;")
            lbl_res_t = QLabel("Resultados del análisis")
            lbl_res_t.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 12px; font-weight: 600;")
            hdr_res.addWidget(ic_chk)
            hdr_res.addWidget(lbl_res_t)
            hdr_res.addStretch()
            res_layout.addLayout(hdr_res)

            # 2 métricas lado a lado
            grid_metrics = QHBoxLayout()
            grid_metrics.setSpacing(8)

            c1 = QFrame()
            c1.setStyleSheet(f"background-color: {Colors.SURFACE_LOWEST}; border-radius: {Radius.SM}px; padding: 6px;")
            c1_l = QVBoxLayout(c1)
            c1_l.setContentsMargins(6, 4, 6, 4)
            c1_l.setSpacing(2)
            c1_sub = QLabel("Registros válidos analizados")
            c1_sub.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px;")
            c1_val = QLabel("124,912 filas")
            c1_val.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 13px; font-weight: bold;")
            c1_l.addWidget(c1_sub)
            c1_l.addWidget(c1_val)
            grid_metrics.addWidget(c1)

            c2 = QFrame()
            c2.setStyleSheet(f"background-color: {Colors.SURFACE_LOWEST}; border-radius: {Radius.SM}px; padding: 6px;")
            c2_l = QVBoxLayout(c2)
            c2_l.setContentsMargins(6, 4, 6, 4)
            c2_l.setSpacing(2)
            c2_sub = QLabel("Ingresos diarios (Percentil 95)")
            c2_sub.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px;")
            c2_val = QLabel("$14,820.50")
            c2_val.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 13px; font-weight: bold;")
            c2_l.addWidget(c2_sub)
            c2_l.addWidget(c2_val)
            grid_metrics.addWidget(c2)

            res_layout.addLayout(grid_metrics)
            b_layout.addWidget(res_frame)

            # 2. Grid de Visual Preview (Gráfico + Artefactos)
            preview_grid = QHBoxLayout()
            preview_grid.setSpacing(10)

            # Tarjeta de Gráfico de Tendencia
            chart_card = QFrame()
            chart_card.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_CONTAINER};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.MD}px;
                }}
                """
            )
            cc_layout = QVBoxLayout(chart_card)
            cc_layout.setContentsMargins(10, 8, 10, 8)
            cc_layout.setSpacing(4)

            hdr_cc = QHBoxLayout()
            lbl_cc_title = QLabel("Curva de Ingresos Diarios (Q3)")
            lbl_cc_title.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 11px; font-weight: 600;")
            lbl_cc_stat = QLabel("+18.4% vs Q2")
            lbl_cc_stat.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px; font-weight: 500;")
            hdr_cc.addWidget(lbl_cc_title)
            hdr_cc.addStretch()
            hdr_cc.addWidget(lbl_cc_stat)
            cc_layout.addLayout(hdr_cc)

            # Gráfico interactivo
            chart_widget = TrendChartWidget()
            cc_layout.addWidget(chart_widget)

            # Footer del gráfico
            ft_cc = QHBoxLayout()
            lbl_w1 = QLabel("Semana 1")
            lbl_w1.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 9.5px;")
            lbl_p95_lim = QLabel("Límite P95 ($14.8k)")
            lbl_p95_lim.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 9.5px; font-weight: 500;")
            lbl_w12 = QLabel("Semana 12")
            lbl_w12.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 9.5px;")
            ft_cc.addWidget(lbl_w1)
            ft_cc.addStretch()
            ft_cc.addWidget(lbl_p95_lim)
            ft_cc.addStretch()
            ft_cc.addWidget(lbl_w12)
            cc_layout.addLayout(ft_cc)

            preview_grid.addWidget(chart_card, stretch=1)

            # Tarjeta de Artefactos Generados
            art_card = QFrame()
            art_card.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_CONTAINER};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.MD}px;
                }}
                """
            )
            ac_box = QVBoxLayout(art_card)
            ac_box.setContentsMargins(10, 8, 10, 8)
            ac_box.setSpacing(6)

            hdr_art = QHBoxLayout()
            lbl_art_t = QLabel("Archivos generados")
            lbl_art_t.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 11px; font-weight: 600;")
            lbl_art_cnt = QLabel("2 elementos")
            lbl_art_cnt.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px;")
            hdr_art.addWidget(lbl_art_t)
            hdr_art.addStretch()
            hdr_art.addWidget(lbl_art_cnt)
            ac_box.addLayout(hdr_art)

            # Archivo 1
            f1 = QFrame()
            f1.setStyleSheet(f"background-color: {Colors.SURFACE_LOWEST}; border-radius: {Radius.SM}px; padding: 4px 8px;")
            f1_l = QHBoxLayout(f1)
            f1_l.setContentsMargins(6, 4, 6, 4)
            lbl_f1_n = QLabel("metricas.parquet")
            lbl_f1_n.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 11px; font-weight: 500;")
            lbl_f1_s = QLabel("3.4 MB")
            lbl_f1_s.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            f1_l.addWidget(lbl_f1_n)
            f1_l.addStretch()
            f1_l.addWidget(lbl_f1_s)
            ac_box.addWidget(f1)

            # Archivo 2
            f2 = QFrame()
            f2.setStyleSheet(f"background-color: {Colors.SURFACE_LOWEST}; border-radius: {Radius.SM}px; padding: 4px 8px;")
            f2_l = QHBoxLayout(f2)
            f2_l.setContentsMargins(6, 4, 6, 4)
            lbl_f2_n = QLabel("resumen_p95.png")
            lbl_f2_n.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 11px; font-weight: 500;")
            lbl_f2_s = QLabel("480 KB")
            lbl_f2_s.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            f2_l.addWidget(lbl_f2_n)
            f2_l.addStretch()
            f2_l.addWidget(lbl_f2_s)
            ac_box.addWidget(f2)

            # Botones inferiores de descarga
            btn_row_art = QHBoxLayout()
            btn_row_art.setSpacing(6)
            btn_see = QPushButton("Ver resultados")
            btn_see.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {Colors.SURFACE_CONTAINER_HIGH};
                    color: {Colors.TEXT_HIGH};
                    border: none;
                    border-radius: {Radius.SM}px;
                    font-size: 10.5px;
                    padding: 4px;
                }}
                """
            )
            btn_dl_all = QPushButton("⬇ Descargar")
            btn_dl_all.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {Colors.PRIMARY_BRIGHT};
                    color: #001E2F;
                    border: none;
                    border-radius: {Radius.SM}px;
                    font-size: 10.5px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
                """
            )
            btn_row_art.addWidget(btn_see, stretch=1)
            btn_row_art.addWidget(btn_dl_all)
            ac_box.addLayout(btn_row_art)

            preview_grid.addWidget(art_card, stretch=1)
            b_layout.addLayout(preview_grid)

        # Action Toolbar para mensajes del Asistente
        if not is_user:
            actions_bar = QHBoxLayout()
            actions_bar.setContentsMargins(0, 4, 0, 0)
            actions_bar.setSpacing(8)

            btn_copy = QPushButton("📋 Copiar")
            btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_copy.setStyleSheet(self._action_btn_qss())
            btn_copy.clicked.connect(self._copy_text)
            actions_bar.addWidget(btn_copy)

            btn_listen = QPushButton("🔊 Escuchar")
            btn_listen.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_listen.setStyleSheet(self._action_btn_qss())
            if self._on_tts_speak:
                btn_listen.clicked.connect(lambda: self._on_tts_speak(self.text))
            actions_bar.addWidget(btn_listen)

            actions_bar.addStretch()

            btn_thumb_up = QPushButton("👍")
            btn_thumb_up.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_thumb_up.setStyleSheet(self._action_icon_btn_qss())
            actions_bar.addWidget(btn_thumb_up)

            btn_thumb_down = QPushButton("👎")
            btn_thumb_down.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_thumb_down.setStyleSheet(self._action_icon_btn_qss())
            actions_bar.addWidget(btn_thumb_down)

            b_layout.addLayout(actions_bar)

        main_layout.addWidget(bubble_box)

    @staticmethod
    def _action_btn_qss() -> str:
        return f"""
        QPushButton {{
            background: transparent;
            border: none;
            color: {Colors.TEXT_LOW};
            font-size: 11px;
            font-weight: 500;
            padding: 3px 6px;
            border-radius: {Radius.SM}px;
        }}
        QPushButton:hover {{
            background-color: {Colors.SURFACE_2};
            color: {Colors.TEXT_HIGH};
        }}
        """

    @staticmethod
    def _action_icon_btn_qss() -> str:
        return f"""
        QPushButton {{
            background: transparent;
            border: none;
            color: {Colors.TEXT_LOW};
            font-size: 12px;
            padding: 3px;
            border-radius: {Radius.SM}px;
        }}
        QPushButton:hover {{
            background-color: {Colors.SURFACE_2};
        }}
        """

    def _copy_text(self) -> None:
        from PyQt6.QtWidgets import QApplication

        cb = QApplication.clipboard()
        if cb:
            cb.setText(self.text)


# ==============================================================================
# PANTALLA PRINCIPAL DE CHAT SIMPLE (Stitch Full View)
# ==============================================================================
class ChatSimpleScreen(QWidget):
    """
    Implementación completa y fiel de 'JARVIS - Chat Simple' (Screen 4).
    """

    send_prompt_requested = pyqtSignal(str)
    voice_toggle_requested = pyqtSignal()
    open_file_requested = pyqtSignal(str)

    def __init__(
        self,
        on_send_prompt: Optional[Callable[[str], None]] = None,
        on_toggle_voice: Optional[Callable[[], None]] = None,
        on_tts_speak: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        Typography.initialize_fonts()
        self._on_send_prompt = on_send_prompt
        self._on_toggle_voice = on_toggle_voice
        self._on_tts_speak = on_tts_speak
        self._thread_items: List[SessionThreadItem] = []

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ----------------------------------------------------------------------
        # 1. Columna lateral de conversaciones (280px)
        # ----------------------------------------------------------------------
        sidebar = QFrame(self)
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_LOWEST};
                border-right: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(12, 16, 12, 16)
        s_layout.setSpacing(12)

        # Header de la lista
        h_box = QHBoxLayout()
        lbl_threads = QLabel("Conversaciones")
        lbl_threads.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_HIGH};")
        h_box.addWidget(lbl_threads)
        h_box.addStretch()
        self.lbl_count = QLabel("5 en total")
        self.lbl_count.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_LOW}; font-family: '{Typography.FONT_FAMILY_MONO}';")
        h_box.addWidget(self.lbl_count)
        s_layout.addLayout(h_box)

        # Botón Nueva Conversación
        self.btn_new_chat = QPushButton("+ Nueva conversación")
        self.btn_new_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_chat.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.PRIMARY};
                color: #FFFFFF;
                border: 1px solid {Colors.PRIMARY};
                border-radius: {Radius.MD}px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Colors.PRIMARY_HOVER};
            }}
            """
        )
        self.btn_new_chat.clicked.connect(self._handle_new_chat)
        s_layout.addWidget(self.btn_new_chat)

        # Barra de búsqueda en historial
        search_box = QFrame()
        search_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
            }}
            """
        )
        sb_layout = QHBoxLayout(search_box)
        sb_layout.setContentsMargins(8, 2, 8, 2)
        sb_layout.setSpacing(6)

        sb_icon = QLabel("🔍")
        sb_icon.setStyleSheet("font-size: 12px;")
        sb_layout.addWidget(sb_icon)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Buscar en el historial...")
        self.input_search.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_HIGH};
                font-size: 12px;
            }}
            """
        )
        self.input_search.textChanged.connect(self._filter_threads)
        sb_layout.addWidget(self.input_search, stretch=1)
        s_layout.addWidget(search_box)

        # Área de Scroll para lista de conversaciones
        scroll_threads = QScrollArea()
        scroll_threads.setWidgetResizable(True)
        scroll_threads.setStyleSheet("background: transparent; border: none;")

        self.threads_container = QWidget()
        self.threads_layout = QVBoxLayout(self.threads_container)
        self.threads_layout.setContentsMargins(0, 0, 0, 0)
        self.threads_layout.setSpacing(4)

        # Grupo: Hoy
        lbl_group_today = QLabel("HOY")
        lbl_group_today.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}'; padding: 6px 4px 2px 4px;"
        )
        self.threads_layout.addWidget(lbl_group_today)

        # Threads mockeados de demostración fieles a Stitch
        self._add_thread_item("t1", "Auditoría de ventas Q3", "Análisis y percentiles calculados", "15m", icon="📊", is_active=True)
        self._add_thread_item("t2", "Revisión de conexión de red", "Socket timeout e interfaces", "2h", icon="🌐")
        self._add_thread_item("t3", "Búsqueda en manuales", "Preguntas frecuentes y RFCs", "5h", icon="📖")

        # Grupo: Ayer
        lbl_group_yesterday = QLabel("AYER")
        lbl_group_yesterday.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}'; padding: 10px 4px 2px 4px;"
        )
        self.threads_layout.addWidget(lbl_group_yesterday)

        self._add_thread_item("t4", "Mantenimiento de seguridad", "Políticas y firewall local", "Ayer", icon="🛡")
        self._add_thread_item("t5", "Optimización del sistema", "Aceleración de buffers y sandbox", "Ayer", icon="⚙")

        self.threads_layout.addStretch()
        scroll_threads.setWidget(self.threads_container)
        s_layout.addWidget(scroll_threads, stretch=1)

        # Footer de la barra lateral: Modo local seguro
        footer_local = QFrame()
        footer_local.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
                padding: 6px;
            }}
            """
        )
        fl_layout = QHBoxLayout(footer_local)
        fl_layout.setContentsMargins(8, 6, 8, 6)
        fl_layout.setSpacing(6)

        dot_sec = QLabel("●")
        dot_sec.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px;")
        fl_layout.addWidget(dot_sec)

        lbl_sec = QLabel("Modo local seguro")
        lbl_sec.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {Colors.TEXT_HIGH};")
        fl_layout.addWidget(lbl_sec)
        fl_layout.addStretch()

        ic_lock = QLabel("🔒")
        ic_lock.setToolTip("Tus datos no salen de este equipo")
        ic_lock.setStyleSheet("font-size: 11px;")
        fl_layout.addWidget(ic_lock)

        s_layout.addWidget(footer_local)
        root_layout.addWidget(sidebar)

        # ----------------------------------------------------------------------
        # 2. Columna Central de Chat Stream
        # ----------------------------------------------------------------------
        center_col = QFrame(self)
        center_col.setStyleSheet(f"background-color: {Colors.CANVAS_BASE};")
        c_layout = QVBoxLayout(center_col)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        # Topbar de Sesión de Chat (h-14 / 56px)
        top_session_bar = QFrame()
        top_session_bar.setFixedHeight(56)
        top_session_bar.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border-bottom: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        tsb_layout = QHBoxLayout(top_session_bar)
        tsb_layout.setContentsMargins(20, 0, 20, 0)
        tsb_layout.setSpacing(12)

        icon_chat = QLabel("💬")
        icon_chat.setFixedSize(34, 34)
        icon_chat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_chat.setStyleSheet(
            f"background-color: {Colors.PRIMARY}22; color: {Colors.PRIMARY_BRIGHT}; "
            f"font-size: 16px; border-radius: {Radius.MD}px;"
        )
        tsb_layout.addWidget(icon_chat)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)

        self.lbl_session_title = QLabel("Auditoría de ventas Q3")
        self.lbl_session_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_HIGH};")
        title_col.addWidget(self.lbl_session_title)

        status_row = QHBoxLayout()
        status_row.setSpacing(4)
        dot_ready = QLabel("●")
        dot_ready.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 9px;")
        status_row.addWidget(dot_ready)
        lbl_ready = QLabel("JARVIS está listo")
        lbl_ready.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 11px; font-weight: 500;")
        status_row.addWidget(lbl_ready)
        status_row.addStretch()
        title_col.addLayout(status_row)

        tsb_layout.addLayout(title_col, stretch=1)

        # Botones de control de sesión
        self.btn_reset_chat = QPushButton("⟳ Reiniciar chat")
        self.btn_reset_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_chat.setStyleSheet(self._session_btn_qss())
        self.btn_reset_chat.clicked.connect(self._handle_reset_chat)
        tsb_layout.addWidget(self.btn_reset_chat)

        self.btn_export_chat = QPushButton("📥 Exportar")
        self.btn_export_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_chat.setStyleSheet(self._session_btn_qss())
        self.btn_export_chat.clicked.connect(self._handle_export_chat)
        tsb_layout.addWidget(self.btn_export_chat)

        self.btn_toggle_sidecar = QPushButton("📂")
        self.btn_toggle_sidecar.setToolTip("Mostrar/Ocultar consola de eventos y auditoría")
        self.btn_toggle_sidecar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sidecar.setFixedSize(32, 32)
        self.btn_toggle_sidecar.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.SURFACE_2};
                color: {Colors.PRIMARY_BRIGHT};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.SM}px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE_3};
                border-color: {Colors.PRIMARY};
            }}
            """
        )
        self.btn_toggle_sidecar.clicked.connect(self._toggle_sidecar_panel)
        tsb_layout.addWidget(self.btn_toggle_sidecar)

        c_layout.addWidget(top_session_bar)

        # Área de Stream de Mensajes
        self.messages_scroll = QScrollArea()
        self.messages_scroll.setWidgetResizable(True)
        self.messages_scroll.setStyleSheet("background: transparent; border: none;")

        # Contenedor centrado max-w-prompt-max-width (768px)
        self.stream_wrapper = QWidget()
        stream_wrapper_layout = QHBoxLayout(self.stream_wrapper)
        stream_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        stream_wrapper_layout.setSpacing(0)

        stream_wrapper_layout.addStretch(1)

        self.messages_container = QWidget()
        self.messages_container.setMaximumWidth(768)
        self.messages_container.setMinimumWidth(500)
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(16, 20, 16, 20)
        self.messages_layout.setSpacing(18)

        # Privacy Pill centrado
        pill_row = QHBoxLayout()
        pill_row.addStretch()
        privacy_pill = QLabel("🛡 Procesado de forma 100% privada y local")
        privacy_pill.setStyleSheet(
            f"background-color: {Colors.SURFACE_2}; color: {Colors.TEXT_MEDIUM}; "
            f"border: 1px solid {Colors.BORDER_STRUCTURAL}; border-radius: {Radius.FULL}px; "
            f"padding: 4px 14px; font-size: 11px; font-weight: 500;"
        )
        pill_row.addWidget(privacy_pill)
        pill_row.addStretch()
        self.messages_layout.addLayout(pill_row)

        # Demo Stitch Messages iniciales
        self._load_demo_messages()

        self.messages_layout.addStretch(1)
        stream_wrapper_layout.addWidget(self.messages_container, stretch=10)
        stream_wrapper_layout.addStretch(1)

        self.messages_scroll.setWidget(self.stream_wrapper)
        c_layout.addWidget(self.messages_scroll, stretch=1)

        # ----------------------------------------------------------------------
        # 3. Footer / Composer Amplio
        # ----------------------------------------------------------------------
        composer_frame = QFrame()
        composer_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border-top: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        comp_layout = QVBoxLayout(composer_frame)
        comp_layout.setContentsMargins(24, 12, 24, 16)
        comp_layout.setSpacing(8)

        # Caja del editor de texto
        composer_box = QFrame()
        composer_box.setMaximumWidth(768)
        composer_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_2};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.LG}px;
            }}
            """
        )
        cb_layout = QVBoxLayout(composer_box)
        cb_layout.setContentsMargins(12, 10, 12, 8)
        cb_layout.setSpacing(6)

        self.input_composer = QPlainTextEdit()
        self.input_composer.setPlaceholderText(
            "Escríbele a JARVIS... (ej. analiza mis ventas, resume un documento, explica un cálculo)"
        )
        self.input_composer.setFixedHeight(64)
        self.input_composer.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_HIGH};
                font-size: 13.5px;
                line-height: 1.4;
            }}
            """
        )
        cb_layout.addWidget(self.input_composer)

        # Barra de acciones inferiores del composer
        comp_actions = QHBoxLayout()
        comp_actions.setContentsMargins(0, 4, 0, 0)
        comp_actions.setSpacing(8)

        self.btn_attach = QPushButton("📎 Adjuntar archivo")
        self.btn_attach.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_attach.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_LOW};
                font-size: 12px;
                padding: 4px 8px;
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE_3};
                color: {Colors.PRIMARY_BRIGHT};
            }}
            """
        )
        self.btn_attach.clicked.connect(self._handle_attach_file)
        comp_actions.addWidget(self.btn_attach)

        self.btn_voice = QPushButton("🎙 Voz")
        self.btn_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voice.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Colors.TEXT_LOW};
                font-size: 12px;
                padding: 4px 8px;
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE_3};
                color: {Colors.SECONDARY};
            }}
            """
        )
        self.btn_voice.clicked.connect(self._handle_toggle_voice)
        comp_actions.addWidget(self.btn_voice)

        comp_actions.addStretch()

        self.btn_send = QPushButton("➔")
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setFixedSize(34, 34)
        self.btn_send.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.PRIMARY};
                color: #FFFFFF;
                border: 1px solid {Colors.PRIMARY};
                border-radius: {Radius.MD}px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.PRIMARY_HOVER};
            }}
            """
        )
        self.btn_send.clicked.connect(self._handle_send)
        comp_actions.addWidget(self.btn_send)

        cb_layout.addLayout(comp_actions)

        # Centrar composer container
        wrap_comp = QHBoxLayout()
        wrap_comp.addStretch(1)
        wrap_comp.addWidget(composer_box, stretch=10)
        wrap_comp.addStretch(1)
        comp_layout.addLayout(wrap_comp)

        c_layout.addWidget(composer_frame)
        root_layout.addWidget(center_col, stretch=1)

        # ----------------------------------------------------------------------
        # 4. Panel Lateral de Telemetría y Contexto (Sidecar / 320px - Stitch)
        # ----------------------------------------------------------------------
        self.sidecar_panel = QFrame(self)
        self.sidecar_panel.setFixedWidth(320)
        self.sidecar_panel.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_1};
                border-left: 1px solid {Colors.BORDER_STRUCTURAL};
            }}
            """
        )
        sidecar_layout = QVBoxLayout(self.sidecar_panel)
        sidecar_layout.setContentsMargins(14, 14, 14, 14)
        sidecar_layout.setSpacing(10)

        # Header Sidecar
        s_header = QHBoxLayout()
        ic_s_folder = QLabel("📁")
        ic_s_folder.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 14px;")
        lbl_s_title = QLabel("Archivos (3)")
        lbl_s_title.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 13px; font-weight: bold;")
        s_header.addWidget(ic_s_folder)
        s_header.addWidget(lbl_s_title)
        s_header.addStretch()

        btn_close_s = QPushButton("✕")
        btn_close_s.setFixedSize(20, 20)
        btn_close_s.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_LOW}; border: none; font-size: 12px;"
        )
        btn_close_s.clicked.connect(lambda: self.sidecar_panel.hide())
        s_header.addWidget(btn_close_s)
        sidecar_layout.addLayout(s_header)

        # Lista de Archivos de la Sesión
        lbl_session_files = QLabel("ARCHIVOS DE ESTA SESIÓN")
        lbl_session_files.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 10px; font-weight: bold; "
            f"font-family: '{Typography.FONT_FAMILY_MONO}'; letter-spacing: 0.5px;"
        )
        sidecar_layout.addWidget(lbl_session_files)

        files_box = QVBoxLayout()
        files_box.setSpacing(6)

        session_files = [
            ("analisis_q3.py", "Script Python · 2.1 KB", "👁", Colors.SECONDARY),
            ("metricas.parquet", "Datos limpios · 3.4 MB", "⬇", Colors.PRIMARY_BRIGHT),
            ("resumen_p95.png", "Gráfico resumen · 480 KB", "↗", Colors.PRIMARY_BRIGHT),
        ]

        for fname, fmeta, icon_btn, accent_col in session_files:
            fc = QFrame()
            fc.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {Colors.SURFACE_CONTAINER};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                    border-radius: {Radius.SM}px;
                }}
                QFrame:hover {{
                    border-color: {Colors.PRIMARY_BRIGHT}44;
                }}
                """
            )
            fcl = QHBoxLayout(fc)
            fcl.setContentsMargins(8, 6, 8, 6)
            fcl.setSpacing(8)

            txt_col = QVBoxLayout()
            txt_col.setContentsMargins(0, 0, 0, 0)
            txt_col.setSpacing(1)
            lbl_fn = QLabel(fname)
            lbl_fn.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 11.5px; font-weight: 600;")
            lbl_fm = QLabel(fmeta)
            lbl_fm.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
            txt_col.addWidget(lbl_fn)
            txt_col.addWidget(lbl_fm)
            fcl.addLayout(txt_col, stretch=1)

            btn_act = QPushButton(icon_btn)
            btn_act.setFixedSize(24, 24)
            btn_act.setStyleSheet(f"background: transparent; border: none; color: {accent_col}; font-size: 12px;")
            fcl.addWidget(btn_act)
            files_box.addWidget(fc)

        sidecar_layout.addLayout(files_box)

        # Telemetría de Sandbox (Memoria + Confinamiento)
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_CONTAINER};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.SM}px;
            }}
            """
        )
        tf_layout = QVBoxLayout(telemetry_frame)
        tf_layout.setContentsMargins(8, 8, 8, 8)
        tf_layout.setSpacing(6)

        hdr_t = QHBoxLayout()
        lbl_t_title = QLabel("TELEMETRÍA SANDBOX")
        lbl_t_title.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 10.5px; font-weight: bold;")
        lbl_t_tag = QLabel("Técnico")
        lbl_t_tag.setStyleSheet(
            f"background-color: {Colors.SURFACE_LOWEST}; color: {Colors.TEXT_LOW}; "
            f"font-size: 9.5px; padding: 1px 4px; border-radius: 2px;"
        )
        hdr_t.addWidget(lbl_t_title)
        hdr_t.addStretch()
        hdr_t.addWidget(lbl_t_tag)
        tf_layout.addLayout(hdr_t)

        # RAM Meter
        ram_row = QHBoxLayout()
        lbl_ram_lbl = QLabel("Memoria Sandbox")
        lbl_ram_lbl.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px;")
        lbl_ram_val = QLabel("3.2 / 8.0 GB")
        lbl_ram_val.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; font-weight: bold;")
        ram_row.addWidget(lbl_ram_lbl)
        ram_row.addStretch()
        ram_row.addWidget(lbl_ram_val)
        tf_layout.addLayout(ram_row)

        ram_bar_bg = QFrame()
        ram_bar_bg.setFixedHeight(4)
        ram_bar_bg.setStyleSheet(f"background-color: {Colors.SURFACE_LOWEST}; border-radius: 2px;")
        ram_bar_fill = QFrame(ram_bar_bg)
        ram_bar_fill.setGeometry(0, 0, 110, 4)
        ram_bar_fill.setStyleSheet(f"background-color: {Colors.SECONDARY}; border-radius: 2px;")
        tf_layout.addWidget(ram_bar_bg)

        # Reglas de confinamiento
        rules_box = QFrame()
        rules_box.setStyleSheet(f"background-color: {Colors.SURFACE_LOWEST}; border-radius: {Radius.SM}px; padding: 4px;")
        rb_layout = QVBoxLayout(rules_box)
        rb_layout.setContentsMargins(4, 4, 4, 4)
        rb_layout.setSpacing(2)

        r1 = QHBoxLayout()
        lbl_r1_k = QLabel("NET_OUTBOUND:")
        lbl_r1_k.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 9.5px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        lbl_r1_v = QLabel("DISABLED")
        lbl_r1_v.setStyleSheet(f"color: {Colors.ERROR}; font-size: 9.5px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}';")
        r1.addWidget(lbl_r1_k)
        r1.addStretch()
        r1.addWidget(lbl_r1_v)
        rb_layout.addLayout(r1)

        r2 = QHBoxLayout()
        lbl_r2_k = QLabel("ROOT_FS:")
        lbl_r2_k.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 9.5px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        lbl_r2_v = QLabel("READ_ONLY")
        lbl_r2_v.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 9.5px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}';")
        r2.addWidget(lbl_r2_k)
        r2.addStretch()
        r2.addWidget(lbl_r2_v)
        rb_layout.addLayout(r2)

        r3 = QHBoxLayout()
        lbl_r3_k = QLabel("GPU_OFFLOAD:")
        lbl_r3_k.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 9.5px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        lbl_r3_v = QLabel("CUDA:0")
        lbl_r3_v.setStyleSheet(f"color: {Colors.PRIMARY_BRIGHT}; font-size: 9.5px; font-weight: bold; font-family: '{Typography.FONT_FAMILY_MONO}';")
        r3.addWidget(lbl_r3_k)
        r3.addStretch()
        r3.addWidget(lbl_r3_v)
        rb_layout.addLayout(r3)

        tf_layout.addWidget(rules_box)
        sidecar_layout.addWidget(telemetry_frame)

        # Consola de Eventos y Auditoría
        lbl_log_hdr = QLabel("LOG DE AUDITORÍA & EVENTOS")
        lbl_log_hdr.setStyleSheet(
            f"color: {Colors.TEXT_LOW}; font-size: 10px; font-weight: bold; "
            f"font-family: '{Typography.FONT_FAMILY_MONO}'; letter-spacing: 0.5px;"
        )
        sidecar_layout.addWidget(lbl_log_hdr)

        self.console_log = QTextEdit(self.sidecar_panel)
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {Colors.SURFACE_LOWEST};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.SM}px;
                color: {Colors.PRIMARY_BRIGHT};
                font-family: '{Typography.FONT_FAMILY_MONO}';
                font-size: 10.5px;
                padding: 6px;
            }}
            """
        )
        sidecar_layout.addWidget(self.console_log, stretch=1)

        # Botón inferior de descarga global
        btn_dl_all_side = QPushButton("⬇ Descargar todos los archivos")
        btn_dl_all_side.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dl_all_side.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.SURFACE_CONTAINER};
                color: {Colors.TEXT_HIGH};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.SM}px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE_CONTAINER_HIGH};
            }}
            """
        )
        sidecar_layout.addWidget(btn_dl_all_side)

        root_layout.addWidget(self.sidecar_panel)
        self.sidecar_panel.hide()

    # ==========================================================================
    # Helpers y Gestión de Mensajes
    # ==========================================================================
    def _add_thread_item(
        self,
        thread_id: str,
        title: str,
        subtitle: str,
        time_ago: str,
        icon: str = "💬",
        is_active: bool = False,
    ) -> None:
        item = SessionThreadItem(thread_id, title, subtitle, time_ago, icon=icon, is_active=is_active)
        item.clicked.connect(self._select_thread)
        self._thread_items.append(item)
        self.threads_layout.addWidget(item)

    def _select_thread(self, thread_id: str) -> None:
        for it in self._thread_items:
            it.set_active(it.thread_id == thread_id)
            if it.thread_id == thread_id:
                self.lbl_session_title.setText(it.lbl_title.text())

    def _filter_threads(self, query: str) -> None:
        q = query.strip().lower()
        for it in self._thread_items:
            if not q or q in it.lbl_title.text().lower() or q in it.lbl_subtitle.text().lower():
                it.show()
            else:
                it.hide()

    def _load_demo_messages(self) -> None:
        """Carga la conversación demostrativa idéntica a Stitch."""
        # 1. Mensaje del Usuario
        user_msg = (
            "JARVIS, analiza el lote de transacciones de ventas del Q3 alojado en ventas_q3.csv. "
            "Limpia los registros nulos, calcula el percentil 95 de ingresos diarios y genera un gráfico resumen en PNG junto con un extracto parquet."
        )
        card_user = StitchChatMessageCard(
            sender="Operador",
            text=user_msg,
            is_user=True,
            attachment_name="ventas_q3.csv",
            attachment_info="18.4 MB · 128,400 filas",
        )
        self.messages_layout.addWidget(card_user)

        # 2. Mensaje del Asistente
        assistant_msg = (
            "Entendido. He procesado los datos de ventas_q3.csv dentro de un entorno seguro y calculé las métricas principales. "
            "Se filtraron los registros vacíos y se calculó el percentil 95 satisfactoriamente."
        )
        code_example = (
            "import polars as pl\n\n"
            "df = pl.read_csv('ventas_q3.csv')\n"
            "df_clean = df.drop_nulls(subset=['monto_bruto', 'timestamp'])\n"
            "p95 = df_clean.select(pl.col('monto_bruto').quantile(0.95)).item()\n\n"
            "df_clean.write_parquet('metricas.parquet')\n"
            "print(f'Registros válidos: {len(df_clean)} | Percentil 95: ${p95:,.2f}')"
        )
        card_jarvis = StitchChatMessageCard(
            sender="JARVIS",
            text=assistant_msg,
            is_user=False,
            code_snippet=code_example,
            has_preview=True,
            on_tts_speak=self._on_tts_speak,
        )
        self.messages_layout.addWidget(card_jarvis)

    def append_chat_message(self, sender: str, text: str, is_user: bool = False) -> None:
        """Inserta un nuevo mensaje en el feed de chat."""
        card = StitchChatMessageCard(
            sender=sender,
            text=text,
            is_user=is_user,
            on_tts_speak=self._on_tts_speak,
        )
        # Insertar antes del stretch final
        idx = max(0, self.messages_layout.count() - 1)
        self.messages_layout.insertWidget(idx, card)
        QTimer.singleShot(60, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self.messages_scroll.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    # ==========================================================================
    # Acciones de Usuario
    # ==========================================================================
    def _handle_send(self) -> None:
        text = self.input_composer.toPlainText().strip()
        if not text:
            return
        self.input_composer.clear()
        self.append_chat_message("Operador", text, is_user=True)
        self.send_prompt_requested.emit(text)
        if self._on_send_prompt:
            self._on_send_prompt(text)

    def _handle_attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo para JARVIS")
        if path:
            self.open_file_requested.emit(path)
            fn = Path(path).name
            self.append_chat_message("Operador", f"[Adjunto cargado: {fn}]", is_user=True)

    def _handle_toggle_voice(self) -> None:
        self.voice_toggle_requested.emit()
        if self._on_toggle_voice:
            self._on_toggle_voice()

    def _handle_new_chat(self) -> None:
        # Limpiar mensajes excepto el pill
        while self.messages_layout.count() > 2:
            item = self.messages_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self.lbl_session_title.setText("Nueva conversación")
        self.append_chat_message("JARVIS", "Sistemas listos. ¿En qué puedo ayudarte hoy?", is_user=False)

    def _handle_reset_chat(self) -> None:
        self._handle_new_chat()

    def _handle_export_chat(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar conversación", "conversacion_jarvis.txt")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"JARVIS — Registro de Conversación\nFecha: {datetime.datetime.now()}\n\n")
                    f.write("Conversación exportada exitosamente.\n")
            except Exception as e:
                pass

    def _toggle_sidecar_panel(self) -> None:
        if self.sidecar_panel.isVisible():
            self.sidecar_panel.hide()
        else:
            self.sidecar_panel.show()

    @staticmethod
    def _session_btn_qss() -> str:
        return f"""
        QPushButton {{
            background-color: {Colors.SURFACE_2};
            color: {Colors.TEXT_MEDIUM};
            border: 1px solid {Colors.BORDER_STRUCTURAL};
            border-radius: {Radius.MD}px;
            padding: 6px 12px;
            font-size: 11px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {Colors.SURFACE_3};
            color: {Colors.TEXT_HIGH};
            border-color: {Colors.PRIMARY};
        }}
        """
