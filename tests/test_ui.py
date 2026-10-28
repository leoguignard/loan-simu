"""Smoke test: build the window offscreen and drive both modes."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from loan_simu.ui import theme
        cls.app = QApplication.instance() or QApplication([])
        theme.apply(cls.app)

    def setUp(self):
        from loan_simu.ui.app import MainWindow
        self.window = MainWindow()

    def test_simple_mode_shows_debt_ratio(self):
        page = self.window.simple
        page.income.setValue(2_000)
        page.recalculate()
        self.assertEqual(page.k_debt.value.text(), "21,23 %")  # 424,50 € / 2 000 €
        self.assertEqual(page.table.rowCount(), len(page.DURATIONS))

    def test_simple_mode_without_income(self):
        page = self.window.simple
        page.income.setValue(0)
        page.recalculate()
        self.assertEqual(page.k_debt.value.text(), "—")

    def test_advanced_mode_full_options(self):
        page = self.window.advanced
        page.eco.setChecked(True)
        page.prepay.setChecked(True)
        page.deferral.setCurrentIndex(1)
        page.recalculate()
        self.assertTrue(page.prepay_card.isVisibleTo(page))
        for view in range(3):
            page.view_loan.group.button(view).click()
            self.assertGreater(page.model.rowCount(), 0)

    def test_dot_decimal_input(self):
        field = self.window.simple.rate
        field.lineEdit().setText("3.75 %")
        field.interpretText()
        self.assertAlmostEqual(field.value(), 3.75)


if __name__ == "__main__":
    unittest.main()
