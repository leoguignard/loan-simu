"""Simple mode: a handful of inputs, the key figures and a duration comparison."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import core
from ..core import LoanParams, Project, simulate
from . import theme
from .charts import Donut
from .widgets import (
    Alert, Card, DebtKpi, KeyValues, Kpi, NumberField, debt_tone, eur, label, pct,
)


class SimplePage(QWidget):
    DURATIONS = (3, 5, 7, 10, 12, 15, 20, 25)

    def __init__(self):
        super().__init__()
        self._timer = QTimer(self, singleShot=True, interval=120, timeout=self.recalculate)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # ---- inputs
        left = QWidget()
        left.setFixedWidth(330)
        col = QVBoxLayout(left)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(16)
        project = Card("Your project")
        self.works = NumberField(30_000, " €")
        self.down = NumberField(0, " €")
        self.years = NumberField(7, " years", maximum=30, minimum=1)
        self.rate = NumberField(4.5, " %", decimals=2, maximum=30, step=0.05)
        self.insurance = NumberField(0.30, " %", decimals=2, maximum=5, step=0.01)
        project.field("Works cost", self.works)
        project.field("Down payment (apport)", self.down)
        project.field("Duration", self.years)
        project.field("Interest rate (nominal)", self.rate)
        project.field("Borrower insurance", self.insurance)
        col.addWidget(project)

        budget = Card("Your budget", "Used to compute your debt ratio (taux d'endettement).")
        self.income = NumberField(4_000, " €")
        self.existing = NumberField(0, " €")
        budget.field("Net income / month", self.income)
        budget.field("Other loans / month", self.existing)
        col.addWidget(budget)

        col.addWidget(label(
            "Insurance is computed on the initial capital. Up to 75 000 € the loan is treated as a "
            "personal renovation loan (crédit conso), above as a real-estate loan.\n\n"
            "Switch to “In depth” for fees, grants, éco-PTZ, deferral and early repayment.",
            "caption", wrap=True))
        col.addStretch()
        root.addWidget(left)

        # ---- results
        right = QVBoxLayout()
        right.setSpacing(16)
        kpis = QHBoxLayout()
        kpis.setSpacing(16)
        self.k_monthly = Kpi("Monthly payment, insurance included", hero=True)
        self.k_cost = Kpi("Total cost of credit")
        self.k_apr = Kpi("APR · TAEG")
        self.k_debt = DebtKpi()
        for k in (self.k_monthly, self.k_cost, self.k_apr, self.k_debt):
            kpis.addWidget(k, 1)
        right.addLayout(kpis)

        self.alert = Alert()
        right.addWidget(self.alert)

        breakdown = Card("Where your money goes")
        inner = QHBoxLayout()
        inner.setSpacing(20)
        self.donut = Donut()
        self.donut.setFixedSize(190, 190)
        inner.addWidget(self.donut)
        self.details = KeyValues()
        for key, text in [("amount", "Amount borrowed"), ("kind", "Loan type"),
                          ("instalment", "Instalment excl. insurance"), ("ins_month", "Insurance / month"),
                          ("interest", "Total interest"), ("ins_total", "Total insurance"),
                          ("usury", "Usury rate (taux d'usure)")]:
            self.details.add(key, text)
        self.details.separator()
        self.details.add("repaid", "Total repaid", strong=True)
        inner.addWidget(self.details, 1)
        breakdown.body.addLayout(inner)
        right.addWidget(breakdown)

        compare = Card("Compare durations", "Click a row to use that duration.")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Duration", "Monthly", "Total interest", "Total cost",
                                              "APR", "Debt ratio"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.cellClicked.connect(self._pick_duration)
        compare.body.addWidget(self.table)
        right.addWidget(compare, 1)
        root.addLayout(right, 1)

        for field in (self.works, self.down, self.years, self.rate, self.insurance, self.income,
                      self.existing):
            field.valueChanged.connect(self._timer.start)
        self.recalculate()

    def _simulate(self, months: int) -> core.Simulation:
        works, down = self.works.value(), self.down.value()
        kind = core.CONSUMER if works - down <= core.CONSUMER_LOAN_CEILING else core.MORTGAGE
        main = LoanParams(0, self.rate.value(), months, kind=kind, insurance_rate=self.insurance.value())
        return simulate(Project(works, main, down_payment=down, monthly_income=self.income.value(),
                                existing_debt=self.existing.value()))

    def _pick_duration(self, row: int, _col: int) -> None:
        self.years.setValue(self._durations[row])

    def recalculate(self) -> None:
        years = self.years.value()
        sim = self._simulate(round(years * 12))
        self.alert.show_messages(sim.warnings)
        self.k_debt.show(sim)
        s = sim.main
        if not s:
            for k in (self.k_monthly, self.k_cost, self.k_apr):
                k.set("—")
            self.details.clear()
            self.donut.plot(None)
            self.table.setRowCount(0)
            return

        first = s.rows[0]
        self.k_monthly.set(eur(first.payment + first.insurance),
                           f"{eur(first.payment)} + {eur(first.insurance)} insurance")
        self.k_cost.set(eur(sim.total_cost, 0), f"Interest {eur(s.total_interest, 0)} · "
                                                f"insurance {eur(s.total_insurance, 0)}")
        over = sim.apr is not None and sim.usury_rate is not None and sim.apr > sim.usury_rate
        self.k_apr.set(pct(sim.apr), f"Legal maximum (usure): {pct(sim.usury_rate)}", "bad" if over else None)

        d = self.details
        d.set("amount", eur(s.principal))
        d.set("kind", "Personal (conso)" if s.principal <= core.CONSUMER_LOAN_CEILING else "Real-estate")
        d.set("instalment", eur(first.payment))
        d.set("ins_month", eur(first.insurance))
        d.set("interest", eur(s.total_interest))
        d.set("ins_total", eur(s.total_insurance))
        d.set("usury", pct(sim.usury_rate))
        d.set("repaid", eur(s.total_paid))
        self.donut.plot(s)
        self._fill_comparison(sim, years)

    def _fill_comparison(self, current: core.Simulation, years: float) -> None:
        p = theme.current()
        self._durations = sorted(set(self.DURATIONS) | {years})
        self.table.setRowCount(len(self._durations))
        self.table.setMinimumHeight(self.table.horizontalHeader().height() + 28 * len(self._durations) + 4)
        bold = QFont(self.table.font())
        bold.setBold(True)
        for row, y in enumerate(self._durations):
            sim = current if y == years else self._simulate(round(y * 12))
            r0 = sim.main.rows[0]
            cells = [f"{y:g} years", eur(r0.payment + r0.insurance), eur(sim.total_interest, 0),
                     eur(sim.total_cost, 0), pct(sim.apr), pct(sim.debt_ratio)]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment((Qt.AlignmentFlag.AlignLeft if col == 0 else Qt.AlignmentFlag.AlignRight)
                                      | Qt.AlignmentFlag.AlignVCenter)
                if y == years:
                    item.setFont(bold)
                    item.setBackground(QColor(p.accent_soft))
                if col == 5 and (tone := debt_tone(sim.debt_ratio)):
                    item.setForeground(QColor(getattr(p, tone)))
                self.table.setItem(row, col, item)
