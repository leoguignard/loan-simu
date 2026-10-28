"""Main window: header with the mode switch, and the two pages."""
from __future__ import annotations

import sys

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from . import theme
from .advanced import AdvancedPage
from .simple import SimplePage
from .widgets import FR, Segmented, label


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prêt travaux – renovation loan simulator")
        self.resize(1440, 900)
        self.setMinimumSize(1180, 760)

        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(18)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = label("Prêt travaux")
        title.setObjectName("AppTitle")
        titles.addWidget(title)
        titles.addWidget(label("Renovation loan simulator · France", "muted"))
        header.addLayout(titles)
        header.addStretch()
        self.mode = Segmented(["Simple", "In depth"])
        header.addWidget(self.mode)
        layout.addLayout(header)

        self.simple = SimplePage()
        self.advanced = AdvancedPage()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.simple)
        self.stack.addWidget(self.advanced)
        self.mode.changed.connect(self.stack.setCurrentIndex)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def refresh(self) -> None:
        """Redraw what is painted with theme colours (charts, gauges, table highlights)."""
        self.simple.recalculate()
        self.advanced.recalculate()
        self.update()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Prêt travaux")
    app.setStyle("Fusion")
    QLocale.setDefault(FR)
    theme.apply(app)
    window = MainWindow()

    def on_scheme_changed(*_):
        theme.apply(app)
        window.refresh()

    app.styleHints().colorSchemeChanged.connect(on_scheme_changed)
    window.show()
    sys.exit(app.exec())
