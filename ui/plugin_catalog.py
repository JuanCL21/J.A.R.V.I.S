"""
Catálogo Curado de Plugins para JARVIS.
Adaptado fielmente al diseño de Stitch: 'JARVIS - Catálogo de Plugins (Unificado)' (ID: f4c7c62fbb0e495d8ef2c3169a81e2f4).

Reglas de arquitectura y seguridad:
- Pantalla para el usuario final: instalar plugins con un clic en "AGREGAR",
  sin exponer jamás datos técnicos de instalación (commit_hash, source_url, reviewed_by, status interno).
- Consume exclusivamente las dos funciones públicas del backend:
    from core import list_curated_plugins, install_from_catalog
- Utiliza la paleta y tipografía del sistema unificado en ui.theme.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import (
    CuratedPluginInfo,
    InstallResult,
    install_from_catalog,
    list_curated_plugins,
)
from ui.theme import Colors, Radius, Spacing, Typography

# Mapeo de íconos a glifos unicode para respaldo visual
_ICON_GLYPH_FALLBACK = {
    "clock-outline": "🕐",
    "code-braces": "{ }",
    "chart-line": "📈",
    "shield-check": "🛡",
    "database": "🗄",
    "cogs": "⚙",
}
_DEFAULT_ICON_GLYPH = "✦"


def _icon_glyph(icon_id: str) -> str:
    return _ICON_GLYPH_FALLBACK.get(icon_id, _DEFAULT_ICON_GLYPH)


# ==============================================================================
# Tarjeta de Plugin (Glass-Card Fiel a Stitch)
# ==============================================================================
class _PluginCard(QFrame):
    """
    Tarjeta individual de plugin inspirada en Stitch:
    - Cabecera con ícono enmarcado, badge de categoría y badge de estado ('Listo' o 'Activo').
    - Título y descripción legible con espaciado consistente.
    - Tira de metadatos técnicos ('v1.2.0 • Sandbox 6 MB • Local').
    - Botón de acción con 3 estados: 'AGREGAR', 'INSTALANDO...', 'INSTALADO'.
    """

    def __init__(
        self,
        plugin: CuratedPluginInfo,
        on_install_clicked: Callable[["_PluginCard"], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.plugin = plugin
        self.plugin_id = plugin.plugin_id
        self._on_install_clicked = on_install_clicked
        self._is_installed = plugin.is_installed

        self.setObjectName("plugin_card")
        self.setStyleSheet(
            f"""
            QFrame#plugin_card {{
                background-color: {Colors.SURFACE_1};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.LG}px;
            }}
            QFrame#plugin_card:hover {{
                border: 1px solid {Colors.PRIMARY}66;
            }}
            """
        )
        self.setMinimumWidth(260)
        self.setMinimumHeight(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 1. Fila superior: Ícono y Badges
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.icon_box = QLabel(_icon_glyph(plugin.icon))
        self.icon_box.setFixedSize(36, 36)
        self.icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self.icon_box)

        top_row.addStretch()

        # Badges superiores
        self.badge_category = QLabel("Utilidad" if "clock" in plugin.icon else "Sistema")
        self.badge_category.setStyleSheet(
            f"background-color: {Colors.SURFACE_LOWEST}; color: {Colors.TEXT_LOW}; "
            f"font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"padding: 3px 6px; border-radius: {Radius.SM}px; border: 1px solid {Colors.BORDER_STRUCTURAL};"
        )
        top_row.addWidget(self.badge_category)

        self.badge_status = QLabel("Activo" if plugin.is_installed else "Listo")
        self.badge_status.setStyleSheet(
            f"font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"padding: 3px 6px; border-radius: {Radius.SM}px;"
        )
        top_row.addWidget(self.badge_status)
        layout.addLayout(top_row)

        # 2. Título y Descripción
        self.lbl_name = QLabel(plugin.name)
        self.lbl_name.setStyleSheet(
            f"color: {Colors.TEXT_HIGH}; font-size: 14px; font-weight: 700; letter-spacing: 0.2px;"
        )
        self.lbl_name.setWordWrap(True)
        layout.addWidget(self.lbl_name)

        self.lbl_desc = QLabel(plugin.description)
        self.lbl_desc.setStyleSheet(
            f"color: {Colors.TEXT_MEDIUM}; font-size: 11.5px; line-height: 1.4;"
        )
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc, stretch=1)

        # 3. Tira de metadatos técnicos (sandbox strip)
        meta_strip = QHBoxLayout()
        meta_strip.setContentsMargins(0, 4, 0, 4)
        meta_strip.setSpacing(6)

        lbl_ver = QLabel("v1.2.0")
        lbl_ver.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        meta_strip.addWidget(lbl_ver)

        lbl_sep1 = QLabel("•")
        lbl_sep1.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px;")
        meta_strip.addWidget(lbl_sep1)

        lbl_sbx = QLabel("Sandbox 6 MB")
        lbl_sbx.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        meta_strip.addWidget(lbl_sbx)

        lbl_sep2 = QLabel("•")
        lbl_sep2.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 10px;")
        meta_strip.addWidget(lbl_sep2)

        lbl_loc = QLabel("Local")
        lbl_loc.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; font-weight: 600;")
        meta_strip.addWidget(lbl_loc)

        meta_strip.addStretch()
        layout.addLayout(meta_strip)

        # 4. Mensaje transitorio de estado
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 10.5px;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # 5. Botón de Acción
        self.action_btn = QPushButton()
        self.action_btn.setFixedHeight(34)
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.clicked.connect(lambda: self._on_install_clicked(self))
        layout.addWidget(self.action_btn)

        self.set_installed(plugin.is_installed)

    def set_installed(self, is_installed: bool) -> None:
        """Refleja el estado instalado/disponible en el botón y badges."""
        self._is_installed = is_installed
        if is_installed:
            self.icon_box.setStyleSheet(
                f"background-color: {Colors.SECONDARY}18; color: {Colors.SECONDARY}; "
                f"font-size: 18px; border-radius: {Radius.SM}px; border: 1px solid {Colors.SECONDARY}44;"
            )
            self.badge_status.setText("Activo")
            self.badge_status.setStyleSheet(
                f"background-color: {Colors.SECONDARY}22; color: {Colors.SECONDARY}; "
                f"border: 1px solid {Colors.SECONDARY}44; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; padding: 3px 6px; border-radius: {Radius.SM}px;"
            )
            self.action_btn.setText("INSTALADO")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {Colors.SECONDARY}18;
                    color: {Colors.SECONDARY};
                    border: 1px solid {Colors.SECONDARY}55;
                    border-radius: {Radius.MD}px;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }}
                """
            )
        else:
            self.icon_box.setStyleSheet(
                f"background-color: {Colors.PRIMARY}18; color: {Colors.PRIMARY_BRIGHT}; "
                f"font-size: 18px; border-radius: {Radius.SM}px; border: 1px solid {Colors.PRIMARY}44;"
            )
            self.badge_status.setText("Listo")
            self.badge_status.setStyleSheet(
                f"background-color: {Colors.SURFACE_2}; color: {Colors.TEXT_MEDIUM}; "
                f"border: 1px solid {Colors.BORDER_STRUCTURAL}; font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; padding: 3px 6px; border-radius: {Radius.SM}px;"
            )
            self.action_btn.setText("AGREGAR")
            self.action_btn.setEnabled(True)
            self.action_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {Colors.PRIMARY}18;
                    color: {Colors.PRIMARY_BRIGHT};
                    border: 1px solid {Colors.PRIMARY}66;
                    border-radius: {Radius.MD}px;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }}
                QPushButton:hover {{
                    background-color: {Colors.PRIMARY};
                    color: #FFFFFF;
                }}
                QPushButton:disabled {{
                    background-color: {Colors.SURFACE_2};
                    color: {Colors.TEXT_LOW};
                    border: 1px solid {Colors.BORDER_STRUCTURAL};
                }}
                """
            )

    def set_installing(self) -> None:
        """Estado transitorio mientras la instalación está en curso."""
        self.action_btn.setEnabled(False)
        self.action_btn.setText("INSTALANDO...")
        self.action_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.WARNING}22;
                color: {Colors.WARNING};
                border: 1px solid {Colors.WARNING}66;
                border-radius: {Radius.MD}px;
                font-size: 11px;
                font-weight: 700;
            }}
            """
        )
        self.status_label.hide()

    def show_status(self, message: str, success: bool) -> None:
        color = Colors.SECONDARY if success else Colors.ERROR
        self.status_label.setStyleSheet(f"font-size: 11px; color: {color}; font-family: '{Typography.FONT_FAMILY_MONO}';")
        self.status_label.setText(message)
        self.status_label.show()


# ==============================================================================
# PANTALLA PRINCIPAL: CATÁLOGO DE PLUGINS (Stitch Reconstructed)
# ==============================================================================
class PluginCatalogScreen(QWidget):
    """
    Pantalla completa del catálogo de plugins, adaptada fielmente al diseño de Stitch.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_status_message: Optional[Callable[[str, bool], None]] = None,
    ):
        super().__init__(parent)
        Typography.initialize_fonts()
        self._on_status_message = on_status_message
        self._cards: List[_PluginCard] = []
        self._active_filter = "all"
        self._search_query = ""

        self.setStyleSheet(f"background-color: {Colors.CANVAS_BASE};")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(28, 24, 28, 24)
        outer_layout.setSpacing(18)

        # 1. Subheader: Título + Enclave Security Chip
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        # Tag Ecosistema Extensible
        tag_eco = QHBoxLayout()
        tag_eco.setSpacing(6)
        dot_blue = QLabel("●")
        dot_blue.setStyleSheet(f"color: {Colors.PRIMARY_BRIGHT}; font-size: 8px;")
        tag_eco.addWidget(dot_blue)

        lbl_tag = QLabel("ECOSISTEMA EXTENSIBLE")
        lbl_tag.setStyleSheet(
            f"color: {Colors.PRIMARY_BRIGHT}; font-size: 11px; font-weight: bold; "
            f"letter-spacing: 1px; font-family: '{Typography.FONT_FAMILY_MONO}';"
        )
        tag_eco.addWidget(lbl_tag)
        tag_eco.addStretch()
        title_col.addLayout(tag_eco)

        # Título y Subtítulo
        lbl_main_title = QLabel("Módulos y Plugins Locales")
        lbl_main_title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {Colors.TEXT_HIGH};")
        title_col.addWidget(lbl_main_title)

        lbl_main_sub = QLabel("Ampliá las capacidades de JARVIS con ejecución segura en sandbox sin telemetría externa.")
        lbl_main_sub.setStyleSheet(f"font-size: 12px; color: {Colors.TEXT_MEDIUM};")
        title_col.addWidget(lbl_main_sub)

        header_row.addLayout(title_col, stretch=1)

        # Chip de Enclave Seguro
        enclave_chip = QFrame()
        enclave_chip.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_LOWEST};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
                padding: 6px 12px;
            }}
            """
        )
        ec_layout = QHBoxLayout(enclave_chip)
        ec_layout.setContentsMargins(10, 6, 10, 6)
        ec_layout.setSpacing(8)

        ic_shield = QLabel("🛡")
        ic_shield.setStyleSheet(f"color: {Colors.SECONDARY}; font-size: 14px;")
        ec_layout.addWidget(ic_shield)

        lbl_ze = QLabel("Zero Exfiltration")
        lbl_ze.setStyleSheet(f"color: {Colors.TEXT_HIGH}; font-size: 11px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        ec_layout.addWidget(lbl_ze)

        lbl_dot_ec = QLabel("•")
        lbl_dot_ec.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px;")
        ec_layout.addWidget(lbl_dot_ec)

        lbl_posix = QLabel("Aislamiento POSIX")
        lbl_posix.setStyleSheet(f"color: {Colors.TEXT_LOW}; font-size: 11px; font-family: '{Typography.FONT_FAMILY_MONO}';")
        ec_layout.addWidget(lbl_posix)

        header_row.addWidget(enclave_chip)
        outer_layout.addLayout(header_row)

        # 2. Fila Inferior: Filtros de Categoría y Buscador Rápido (Ctrl K)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        # Pills de filtro
        self.btn_filter_all = QPushButton("Todos")
        self.btn_filter_installed = QPushButton("Instalados")
        self.btn_filter_avail = QPushButton("Disponibles")
        self.btn_filter_system = QPushButton("Sistema / Core")

        self.filter_buttons = [
            ("all", self.btn_filter_all),
            ("installed", self.btn_filter_installed),
            ("available", self.btn_filter_avail),
            ("system", self.btn_filter_system),
        ]

        for filter_key, btn in self.filter_buttons:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=filter_key: self._set_filter(k))
            filter_row.addWidget(btn)

        self._update_filter_button_styles()

        filter_row.addStretch()

        # Input de búsqueda rápida
        search_box = QFrame()
        search_box.setFixedWidth(260)
        search_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.SURFACE_LOWEST};
                border: 1px solid {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.MD}px;
            }}
            """
        )
        s_layout = QHBoxLayout(search_box)
        s_layout.setContentsMargins(8, 2, 8, 2)
        s_layout.setSpacing(6)

        s_icon = QLabel("🔍")
        s_icon.setStyleSheet("font-size: 12px;")
        s_layout.addWidget(s_icon)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Buscar plugins...")
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
        self.input_search.textChanged.connect(self._on_search_text_changed)
        s_layout.addWidget(self.input_search, stretch=1)

        badge_shortcut = QLabel("Ctrl K")
        badge_shortcut.setStyleSheet(
            f"background-color: {Colors.SURFACE_2}; color: {Colors.TEXT_LOW}; "
            f"font-size: 10px; font-family: '{Typography.FONT_FAMILY_MONO}'; "
            f"padding: 2px 5px; border-radius: {Radius.XS}px; border: 1px solid {Colors.BORDER_STRUCTURAL};"
        )
        s_layout.addWidget(badge_shortcut)

        filter_row.addWidget(search_box)
        outer_layout.addLayout(filter_row)

        # 3. Label de Estado Vacío (Empty State)
        self._empty_label = QLabel("No se encontraron plugins que coincidan con la búsqueda o filtro.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_LOW};
                font-size: 13px;
                padding: 40px;
                background-color: {Colors.SURFACE_1};
                border: 1px dashed {Colors.BORDER_STRUCTURAL};
                border-radius: {Radius.LG}px;
            }}
            """
        )
        self._empty_label.hide()
        outer_layout.addWidget(self._empty_label)

        # 4. Scroll Area y Grilla de 3 Columnas
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self._grid_container)
        outer_layout.addWidget(scroll, stretch=1)

        self._columns = 3
        self.refresh()

    # ==========================================================================
    # Lógica de Filtros y Búsqueda
    # ==========================================================================
    def _set_filter(self, filter_key: str) -> None:
        self._active_filter = filter_key
        self._update_filter_button_styles()
        self._apply_visibility_filters()

    def _update_filter_button_styles(self) -> None:
        for key, btn in self.filter_buttons:
            if key == self._active_filter:
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {Colors.SURFACE_2};
                        color: {Colors.TEXT_HIGH};
                        border: 1px solid {Colors.BORDER_STRUCTURAL};
                        border-radius: {Radius.MD}px;
                        padding: 6px 14px;
                        font-size: 11.5px;
                        font-weight: 700;
                    }}
                    """
                )
            else:
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {Colors.TEXT_MEDIUM};
                        border: 1px solid transparent;
                        border-radius: {Radius.MD}px;
                        padding: 6px 14px;
                        font-size: 11.5px;
                        font-weight: 500;
                    }}
                    QPushButton:hover {{
                        background-color: {Colors.SURFACE_1};
                        color: {Colors.TEXT_HIGH};
                    }}
                    """
                )

    def _on_search_text_changed(self, text: str) -> None:
        self._search_query = text.strip().lower()
        self._apply_visibility_filters()

    def _apply_visibility_filters(self) -> None:
        visible_count = 0
        for card in self._cards:
            matches_filter = True
            if self._active_filter == "installed":
                matches_filter = card._is_installed
            elif self._active_filter == "available":
                matches_filter = not card._is_installed
            elif self._active_filter == "system":
                matches_filter = card.plugin_id in ("toy", "system_monitor")

            matches_search = True
            if self._search_query:
                q = self._search_query
                matches_search = (
                    q in card.plugin.name.lower() or q in card.plugin.description.lower()
                )

            should_show = matches_filter and matches_search
            card.setVisible(should_show)
            if should_show:
                visible_count += 1

        self._empty_label.setVisible(visible_count == 0)

    # ==========================================================================
    # Carga y Refresco del Backend
    # ==========================================================================
    def refresh(self) -> None:
        """
        Consulta al backend de plugins y reconstruye la grilla con el diseño de Stitch.
        """
        self._clear_grid()
        plugins = list_curated_plugins()

        if not plugins:
            self._empty_label.show()
            return

        self._empty_label.hide()

        # Conteo para badges
        total = len(plugins)
        installed = sum(1 for p in plugins if p.is_installed)
        avail = total - installed

        self.btn_filter_all.setText(f"Todos {total}")
        self.btn_filter_installed.setText(f"Instalados {installed}")
        self.btn_filter_avail.setText(f"Disponibles {avail}")

        for index, plugin in enumerate(plugins):
            card = _PluginCard(plugin, on_install_clicked=self._handle_install_clicked)
            row, col = divmod(index, self._columns)
            self._grid_layout.addWidget(card, row, col)
            self._cards.append(card)

        self._apply_visibility_filters()

    def _clear_grid(self) -> None:
        for card in self._cards:
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    # ==========================================================================
    # Instalación de Plugins
    # ==========================================================================
    def _handle_install_clicked(self, card: _PluginCard) -> None:
        card.set_installing()

        # Llamada síncrona al backend
        result: InstallResult = install_from_catalog(card.plugin_id)

        card.set_installed(result.success or card._is_installed)
        card.show_status(result.message, result.success)

        if self._on_status_message is not None:
            self._on_status_message(result.message, result.success)
