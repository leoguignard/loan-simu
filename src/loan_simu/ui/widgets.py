"""Reusable widgets: number fields, cards, KPI tiles and the debt-ratio gauge."""
from __future__ import annotations

from PySide6.QtCore import QLocale, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import core
from . import theme

FR = QLocale(QLocale.Language.French, QLocale.Country.France)


def eur(x: float, decimals: int = 2) -> str:
    return f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",") + " €"


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f} %".replace(".", ",")


def debt_tone(ratio: float | None) -> str | None:
    if ratio is None:
        return None
    if ratio <= 30:
        return "good"
    return "warn" if ratio <= core.MAX_DEBT_RATIO else "bad"


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def set_tone(widget: QWidget, tone: str | None) -> None:
    """Switch a [tone] style variant (good / warn / bad) and re-apply the stylesheet."""
    widget.setProperty("tone", tone or "")
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class NumberField(QDoubleSpinBox):
    """French-formatted number input that also accepts a dot as decimal separator."""

    def __init__(self, value: float, suffix: str = "", decimals: int = 0, maximum: float = 10_000_000,
                 minimum: float = 0, step: float | None = None):
        super().__init__()
        self.setLocale(FR)
        self.setDecimals(decimals)
        self.setRange(minimum, maximum)
        self.setSuffix(suffix)
        self.setGroupSeparatorShown(True)
        self.setSingleStep(step or (1 if decimals == 0 else 0.1))
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(130)
        self.setValue(value)

    def validate(self, text, pos):
        return super().validate(text.replace(".", ","), pos)

    def valueFromText(self, text):
        return super().valueFromText(text.replace(".", ","))

    def wheelEvent(self, event):
        # Let the page scroll unless the field is being edited.
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class Combo(QComboBox):
    def __init__(self, items: list[str], current: str | None = None):
        super().__init__()
        self.addItems(items)
        if current:
            self.setCurrentText(current)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Fit the column instead of growing to the longest option.
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class Card(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None):
        super().__init__()
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 18)
        self.body.setSpacing(10)
        self._form: QGridLayout | None = None
        if title:
            t = QLabel(title)
            t.setObjectName("CardTitle")
            self.body.addWidget(t)
        if subtitle:
            self.body.addWidget(label(subtitle, "caption", wrap=True))

    def field(self, text: str, widget: QWidget) -> QLabel:
        """Add a 'label … input' row to the card's form grid."""
        if self._form is None:
            self._form = QGridLayout()
            self._form.setHorizontalSpacing(12)
            self._form.setVerticalSpacing(8)
            self._form.setColumnStretch(0, 1)
            self.body.addLayout(self._form)
        row = self._form.rowCount()
        lbl = QLabel(text)
        self._form.addWidget(lbl, row, 0)
        self._form.addWidget(widget, row, 1)
        return lbl

    def wide(self, widget: QWidget) -> None:
        """Add a widget spanning the whole form width."""
        if self._form is None:
            self.body.addWidget(widget)
        else:
            self._form.addWidget(widget, self._form.rowCount(), 0, 1, 2)


class Kpi(Card):
    def __init__(self, caption: str, hero: bool = False):
        super().__init__()
        self.body.setSpacing(4)
        self.body.addWidget(label(caption, "caption"))
        self.value = label("—", "hero" if hero else "kpi")
        self.body.addWidget(self.value)
        self.hint = label("", "caption", wrap=True)
        self.body.addWidget(self.hint)
        self.body.addStretch()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set(self, value: str, hint: str = "", tone: str | None = None) -> None:
        self.value.setText(value)
        self.hint.setText(hint)
        if self.value.property("role") != "hero":
            set_tone(self.value, tone)


class DebtGauge(QWidget):
    """Horizontal bar from 0 to 50 % with a marker at the 35 % HCSF limit."""

    SCALE = 50.0

    def __init__(self):
        super().__init__()
        self.ratio: float | None = None
        self.setMinimumHeight(30)

    def set_ratio(self, ratio: float | None) -> None:
        self.ratio = ratio
        self.update()

    def paintEvent(self, _event):
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, bar_h, y = self.width() - 1, 8.0, 4.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.border))
        painter.drawRoundedRect(QRectF(0, y, w, bar_h), 4, 4)
        if self.ratio is not None:
            painter.setBrush(QColor(getattr(p, debt_tone(self.ratio))))
            fill = max(min(self.ratio / self.SCALE, 1.0) * w, bar_h)
            painter.drawRoundedRect(QRectF(0, y, fill, bar_h), 4, 4)
        x = core.MAX_DEBT_RATIO / self.SCALE * w
        painter.setPen(QPen(QColor(p.text), 2))
        painter.drawLine(QPointF(x, y - 3), QPointF(x, y + bar_h + 3))
        font = QFont(self.font())
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor(p.muted))
        painter.drawText(QRectF(x - 40, y + bar_h + 3, 80, 14), Qt.AlignmentFlag.AlignCenter,
                         f"{core.MAX_DEBT_RATIO:.0f} % max")


class KeyValues(QWidget):
    """Two-column list of labelled values."""

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setVerticalSpacing(7)
        self.grid.setColumnStretch(0, 1)
        self.values: dict[str, QLabel] = {}

    def add(self, key: str, text: str, strong: bool = False) -> None:
        row = self.grid.rowCount()
        name = label(text, "strong" if strong else "muted")
        value = label("—", "strong" if strong else None)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.grid.addWidget(name, row, 0)
        self.grid.addWidget(value, row, 1)
        self.values[key] = value

    def separator(self) -> None:
        line = QFrame()
        line.setFixedHeight(1)
        line.setObjectName("Separator")
        self.grid.addWidget(line, self.grid.rowCount(), 0, 1, 2)

    def set(self, key: str, value: str, tone: str | None = None) -> None:
        self.values[key].setText(value)
        set_tone(self.values[key], tone)

    def clear(self) -> None:
        for lbl in self.values.values():
            lbl.setText("—")


class DebtKpi(Kpi):
    """Debt ratio (taux d'endettement) with its gauge and the money left each month."""

    def __init__(self):
        super().__init__("Debt ratio · taux d'endettement")
        self.gauge = DebtGauge()
        self.body.insertWidget(2, self.gauge)

    def show(self, sim: core.Simulation | None) -> None:
        ratio = sim.debt_ratio if sim else None
        self.gauge.set_ratio(ratio)
        if ratio is None:
            self.set("—", "Enter your net income to compute it")
        else:
            self.set(pct(ratio), f"Left to live on: {eur(sim.remaining_income, 0)} / month", debt_tone(ratio))


class Alert(QLabel):
    """Banner listing warnings, or a reassuring line when everything passes."""

    def __init__(self):
        super().__init__()
        self.setObjectName("Alert")
        self.setWordWrap(True)
        self.hide()

    def show_messages(self, warnings: list[str], ok_text: str | None = None) -> None:
        if warnings:
            self.setText("\n".join(f"⚠  {w}" for w in warnings))
            set_tone(self, None)
        elif ok_text:
            self.setText(f"✓  {ok_text}")
            set_tone(self, "good")
        self.setVisible(bool(warnings or ok_text))


class Segmented(QFrame):
    """Pill-shaped exclusive choice, e.g. Simple | In depth."""

    changed = Signal(int)

    def __init__(self, options: list[str], current: int = 0):
        super().__init__()
        self.setObjectName("Segmented")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.group = QButtonGroup(self)
        for i, text in enumerate(options):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(i == current)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(button, i)
            row.addWidget(button)
        self.group.idClicked.connect(self.changed)

    def index(self) -> int:
        return self.group.checkedId()
