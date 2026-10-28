"""Light and dark palettes, applied as a Qt stylesheet that follows the system theme."""
from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_soft: str
    good: str
    good_soft: str
    warn: str
    warn_soft: str
    bad: str
    bad_soft: str
    principal: str
    interest: str
    insurance: str
    eco: str


LIGHT = Palette(
    dark=False, bg="#f3f4f7", surface="#ffffff", surface_alt="#f6f7f9", border="#e2e5eb",
    text="#1b2130", muted="#6b7385", accent="#2f6bea", accent_soft="#e9f0fe",
    good="#14915b", good_soft="#e5f6ee", warn="#c27803", warn_soft="#fdf4e1",
    bad="#d23c3c", bad_soft="#fdecec",
    principal="#2f6bea", interest="#f0795e", insurance="#33b38a", eco="#e2b23c",
)
DARK = Palette(
    dark=True, bg="#0f1115", surface="#181b22", surface_alt="#20242d", border="#2b303b",
    text="#e8eaf0", muted="#9099ab", accent="#6b9bff", accent_soft="#1d2840",
    good="#3ccf8e", good_soft="#13291f", warn="#f2b43c", warn_soft="#2d2412",
    bad="#ff7b7b", bad_soft="#2f1719",
    principal="#6b9bff", interest="#ff8f73", insurance="#45cf9f", eco="#f2c75c",
)

_current = LIGHT


def current() -> Palette:
    return _current


def apply(app: QApplication) -> Palette:
    """Pick the palette from LOAN_SIMU_THEME (light/dark) or the system, and style the app."""
    global _current
    forced = os.environ.get("LOAN_SIMU_THEME", "").lower()
    if forced in ("light", "dark"):
        dark = forced == "dark"
    else:
        dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    _current = DARK if dark else LIGHT
    app.setPalette(_qpalette(_current))
    app.setStyleSheet(stylesheet(_current))
    return _current


def _qpalette(p: Palette) -> QPalette:
    pal = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, p.bg), (QPalette.ColorRole.WindowText, p.text),
        (QPalette.ColorRole.Base, p.surface_alt), (QPalette.ColorRole.AlternateBase, p.surface),
        (QPalette.ColorRole.Text, p.text), (QPalette.ColorRole.Button, p.surface),
        (QPalette.ColorRole.ButtonText, p.text), (QPalette.ColorRole.Highlight, p.accent),
        (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.ToolTipBase, p.surface),
        (QPalette.ColorRole.ToolTipText, p.text), (QPalette.ColorRole.PlaceholderText, p.muted),
    ]:
        pal.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(p.muted))
    return pal


def stylesheet(p: Palette) -> str:
    return f"""
    QWidget {{ color: {p.text}; font-size: 13px; }}
    #Root {{ background: {p.bg}; }}
    QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 6px; }}

    #AppTitle {{ font-size: 22px; font-weight: 700; }}
    QLabel[role="muted"] {{ color: {p.muted}; }}
    QLabel[role="caption"] {{ color: {p.muted}; font-size: 12px; }}
    QLabel[role="kpi"] {{ font-size: 24px; font-weight: 700; }}
    QLabel[role="hero"] {{ font-size: 30px; font-weight: 700; color: {p.accent}; }}
    QLabel[role="strong"] {{ font-weight: 700; }}
    QLabel[tone="good"] {{ color: {p.good}; }}
    QLabel[tone="warn"] {{ color: {p.warn}; }}
    QLabel[tone="bad"] {{ color: {p.bad}; }}
    QLabel:disabled {{ color: {p.muted}; }}

    #Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; }}
    #CardTitle {{ font-size: 14px; font-weight: 700; }}
    #Separator {{ background: {p.border}; }}

    #Alert {{ border-radius: 10px; padding: 10px 14px; background: {p.bad_soft}; color: {p.bad}; }}
    #Alert[tone="good"] {{ background: {p.good_soft}; color: {p.good}; }}

    QDoubleSpinBox, QComboBox {{
        background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px;
        padding: 6px 10px; min-height: 18px; selection-background-color: {p.accent};
    }}
    QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {p.muted}; }}
    QDoubleSpinBox:focus, QComboBox:focus, QComboBox:on {{ border-color: {p.accent}; }}
    QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {p.muted}; background: {p.surface}; }}
    /* Zero-width arrows: QAbstractSpinBox.NoButtons collapses the editor once a border is styled. */
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface}; border: 1px solid {p.border}; outline: 0; padding: 4px;
        selection-background-color: {p.accent_soft}; selection-color: {p.text};
    }}

    QCheckBox {{ spacing: 8px; font-weight: 600; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 5px;
        border: 1px solid {p.border}; background: {p.surface_alt};
    }}
    QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

    QPushButton {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 7px 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{ border-color: {p.accent}; color: {p.accent}; }}
    #Segmented {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px; }}
    #Segmented QPushButton {{
        background: transparent; border: none; border-radius: 7px; padding: 6px 16px; color: {p.muted};
    }}
    #Segmented QPushButton:hover {{ color: {p.text}; }}
    #Segmented QPushButton:checked {{ background: {p.accent}; color: #ffffff; }}

    QTabWidget::pane {{ border: none; }}
    QTabBar {{ qproperty-drawBase: 0; }}
    QTabBar::tab {{
        background: transparent; color: {p.muted}; padding: 8px 4px; margin-right: 18px;
        border: none; border-bottom: 2px solid transparent; font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: {p.text}; }}
    QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}

    QTableView, QTableWidget {{
        background: {p.surface}; alternate-background-color: {p.surface_alt}; border: none;
        gridline-color: transparent; selection-background-color: {p.accent_soft}; selection-color: {p.text};
    }}
    QTableView::item {{ padding: 0 8px; }}
    QHeaderView::section {{
        background: {p.surface}; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
        padding: 6px 8px; font-weight: 600; font-size: 12px;
    }}
    QTableCornerButton::section {{ background: {p.surface}; border: none; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {p.border}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
    QScrollBar::handle:hover {{ background: {p.muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """
