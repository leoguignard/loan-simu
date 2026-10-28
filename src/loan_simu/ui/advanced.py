"""In-depth mode: every parameter of a French renovation loan, with table and charts."""
from __future__ import annotations

import csv

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QPushButton, QScrollArea,
    QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from .. import core
from ..core import LoanParams, Project, Row, simulate
from .charts import ScheduleCharts
from .widgets import (
    Alert, Card, Combo, DebtKpi, KeyValues, Kpi, NumberField, Segmented, eur, label, pct,
)

KIND_LABELS = {
    core.CONSUMER: "Personal renovation loan (crédit conso)",
    core.MORTGAGE: "Real-estate loan (prêt immobilier)",
}
DEFERRAL_LABELS = {
    core.DEFERRAL_NONE: "No deferral",
    core.DEFERRAL_PARTIAL: "Partial – interest only (différé partiel)",
    core.DEFERRAL_TOTAL: "Total – no payment (différé total)",
}
INSURANCE_BASE_LABELS = {False: "On the initial capital", True: "On the remaining capital (CRD)"}
PREPAY_LABELS = {
    core.REDUCE_DURATION: "Keep payment, shorten the loan",
    core.REDUCE_PAYMENT: "Keep duration, lower the payment",
}
ECO_LABELS = [f"{name} – up to {cap // 1000} k€" for name, cap, _ in core.ECO_PTZ_CATEGORIES]
LOAN_VIEWS = ["All loans", "Main loan", "Éco-PTZ"]


def key_for(labels: dict, text: str):
    return next(k for k, v in labels.items() if v == text)


class ScheduleModel(QAbstractTableModel):
    HEADERS = ["Period", "Instalment", "Interest", "Capital", "Insurance", "Early repaid", "Total paid",
               "Capital left"]

    def __init__(self):
        super().__init__()
        self.rows: list[Row] = []
        self.unit = "Year"

    def set_rows(self, rows: list[Row], unit: str) -> None:
        self.beginResetModel()
        self.rows, self.unit = rows, unit
        self.endResetModel()

    def cells(self, r: Row) -> list:
        return [f"{self.unit} {r.month}", r.payment, r.interest, r.principal, r.insurance, r.prepayment,
                r.total, r.balance]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        if role == Qt.ItemDataRole.TextAlignmentRole and section > 0:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            value = self.cells(self.rows[index.row()])[col]
            if col == 0:
                return value
            return "" if col == 5 and not value else eur(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            h = Qt.AlignmentFlag.AlignLeft if col == 0 else Qt.AlignmentFlag.AlignRight
            return h | Qt.AlignmentFlag.AlignVCenter
        return None


class AdvancedPage(QWidget):
    def __init__(self):
        super().__init__()
        self.sim: core.Simulation | None = None
        self._timer = QTimer(self, singleShot=True, interval=120, timeout=self.recalculate)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(372)
        inputs = QWidget()
        self._inputs = QVBoxLayout(inputs)
        self._inputs.setContentsMargins(0, 0, 12, 0)
        self._inputs.setSpacing(16)
        self._build_inputs()
        self._inputs.addStretch()
        scroll.setWidget(inputs)
        root.addWidget(scroll)

        right = QVBoxLayout()
        right.setSpacing(16)
        kpis = QHBoxLayout()
        kpis.setSpacing(16)
        self.k_monthly = Kpi("Highest monthly payment", hero=True)
        self.k_cost = Kpi("Total cost of credit")
        self.k_apr = Kpi("APR of main loan · TAEG")
        self.k_debt = DebtKpi()
        for k in (self.k_monthly, self.k_cost, self.k_apr, self.k_debt):
            kpis.addWidget(k, 1)
        right.addLayout(kpis)
        self.alert = Alert()
        right.addWidget(self.alert)

        tabs = QTabWidget()
        tabs.addTab(self._build_summary(), "Summary")
        tabs.addTab(self._build_table(), "Amortization table")
        self.charts = ScheduleCharts()
        tabs.addTab(self._wrap(self.charts), "Charts")
        right.addWidget(tabs, 1)
        root.addLayout(right, 1)

        for w in self._watched:
            signal = w.toggled if isinstance(w, QCheckBox) else (
                w.currentIndexChanged if isinstance(w, Combo) else w.valueChanged)
            signal.connect(self._changed)
        self.eco_cat.currentIndexChanged.connect(self._eco_category_selected)
        self._update_states()
        self.recalculate()

    # ---- inputs

    def _card(self, title, subtitle=None) -> Card:
        card = Card(title, subtitle)
        self._inputs.addWidget(card)
        return card

    def _build_inputs(self):
        c = self._card("Project")
        self.works = NumberField(45_000, " €")
        self.down = NumberField(5_000, " €")
        self.grants = NumberField(8_000, " €")
        c.field("Works cost (devis)", self.works)
        c.field("Down payment (apport)", self.down)
        c.field("Grants", self.grants)
        c.wide(label("MaPrimeRénov', CEE, local aid…", "caption"))

        c = self._card("Main loan")
        self.kind = Combo(list(KIND_LABELS.values()))
        c.wide(self.kind)
        self.rate = NumberField(4.9, " %", decimals=2, maximum=30, step=0.05)
        self.years = NumberField(10, " years", decimals=1, maximum=30, minimum=0.5, step=1)
        c.field("Interest rate (nominal)", self.rate)
        c.field("Duration, deferral incl.", self.years)
        self.deferral = Combo(list(DEFERRAL_LABELS.values()))
        c.wide(self.deferral)
        self.deferral_months = NumberField(6, " months", maximum=60)
        self.deferral_label = c.field("Deferral length", self.deferral_months)

        c = self._card("Borrower insurance", "Assurance emprunteur")
        self.ins_rate = NumberField(0.30, " %", decimals=2, maximum=5, step=0.01)
        c.field("Annual rate", self.ins_rate)
        self.ins_base = Combo(list(INSURANCE_BASE_LABELS.values()))
        c.wide(self.ins_base)
        self.coverage = NumberField(100, " %", maximum=200, step=10)
        c.field("Coverage (quotité)", self.coverage)
        c.wide(label("100 % for one borrower, up to 200 % for two.", "caption"))

        c = self._card("Upfront fees")
        self.app_fee = NumberField(150, " €")
        self.guarantee = NumberField(0, " €")
        self.broker = NumberField(0, " €")
        c.field("Bank fee (dossier)", self.app_fee)
        c.field("Guarantee (caution)", self.guarantee)
        c.field("Broker fee (courtage)", self.broker)

        c = self._card("Éco-PTZ", "0 % loan for energy renovation, RGE contractor required.")
        self.eco = QCheckBox("Add an éco-PTZ")
        c.wide(self.eco)
        self.eco_cat = Combo(ECO_LABELS, ECO_LABELS[2])
        c.wide(self.eco_cat)
        self.eco_amount = NumberField(25_000, " €")
        self.eco_years = NumberField(15, " years", maximum=20, minimum=1)
        self.eco_labels = [c.field("Amount", self.eco_amount), c.field("Duration", self.eco_years)]
        self.eco_ins = QCheckBox("Insure it like the main loan")
        self.eco_ins.setChecked(True)
        c.wide(self.eco_ins)

        c = self._card("Household budget", "For the debt ratio (taux d'endettement).")
        self.income = NumberField(4_000, " €")
        self.existing = NumberField(0, " €")
        c.field("Net income / month", self.income)
        c.field("Other loans / month", self.existing)

        c = self._card("Early repayment", "Remboursement anticipé")
        self.prepay = QCheckBox("Simulate an early repayment")
        c.wide(self.prepay)
        self.prepay_month = NumberField(36, "", maximum=360, minimum=1)
        self.prepay_amount = NumberField(10_000, " €")
        self.prepay_labels = [c.field("After month", self.prepay_month), c.field("Amount", self.prepay_amount)]
        self.prepay_mode = Combo(list(PREPAY_LABELS.values()))
        c.wide(self.prepay_mode)

        c = self._card("Usury rate", "Taux d'usure – the legal maximum APR.")
        self.usury_auto = QCheckBox("Banque de France table")
        self.usury_auto.setChecked(True)
        c.wide(self.usury_auto)
        c.wide(label(core.USURY_PERIOD, "caption"))
        self.usury = NumberField(8.56, " %", decimals=2, maximum=50, step=0.01)
        self.usury_label = c.field("Custom rate", self.usury)

        self._watched = [
            self.works, self.down, self.grants, self.kind, self.rate, self.years, self.deferral,
            self.deferral_months, self.ins_rate, self.ins_base, self.coverage, self.app_fee, self.guarantee,
            self.broker, self.eco, self.eco_cat, self.eco_amount, self.eco_years, self.eco_ins, self.income,
            self.existing, self.prepay, self.prepay_month, self.prepay_amount, self.prepay_mode,
            self.usury_auto, self.usury,
        ]

    def _eco_category_selected(self, index: int) -> None:
        _, cap, years = core.ECO_PTZ_CATEGORIES[index]
        self.eco_amount.setValue(cap)
        self.eco_years.setValue(years)

    def _changed(self, *_):
        self._update_states()
        self._timer.start()

    def _update_states(self):
        deferral = self.deferral.currentText() != DEFERRAL_LABELS[core.DEFERRAL_NONE]
        for w in (self.deferral_months, self.deferral_label):
            w.setEnabled(deferral)
        for w in (self.eco_cat, self.eco_amount, self.eco_years, self.eco_ins, *self.eco_labels):
            w.setEnabled(self.eco.isChecked())
        for w in (self.prepay_month, self.prepay_amount, self.prepay_mode, *self.prepay_labels):
            w.setEnabled(self.prepay.isChecked())
        for w in (self.usury, self.usury_label):
            w.setEnabled(not self.usury_auto.isChecked())

    # ---- outputs

    @staticmethod
    def _wrap(widget: QWidget) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 12, 0, 0)
        card = Card()
        card.body.addWidget(widget)
        lay.addWidget(card)
        return page

    def _build_summary(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 12, 4, 0)
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        plan = Card("Financing plan")
        self.plan = KeyValues()
        for key, text in [("works", "Works cost"), ("down", "− Down payment"), ("grants", "− Grants")]:
            self.plan.add(key, text)
        self.plan.separator()
        self.plan.add("to_finance", "Amount to borrow", strong=True)
        self.plan.add("main", "   of which main loan")
        self.plan.add("eco", "   of which éco-PTZ")
        plan.body.addWidget(self.plan)
        grid.addWidget(plan, 0, 0)

        cost = Card("Cost of credit")
        self.cost = KeyValues()
        for key, text in [("interest", "Interest"), ("insurance", "Insurance"), ("fees", "Upfront fees"),
                          ("penalty", "Early repayment penalty (IRA)")]:
            self.cost.add(key, text)
        self.cost.separator()
        self.cost.add("total", "Total cost of credit", strong=True)
        self.cost.add("repaid", "Total repaid, fees included")
        cost.body.addWidget(self.cost)
        grid.addWidget(cost, 0, 1)

        payments = Card("Monthly payments", "Each period where the amount you pay stays the same.")
        holder = QWidget()
        self.phase_grid = QGridLayout(holder)
        self.phase_grid.setContentsMargins(0, 0, 0, 0)
        self.phase_grid.setVerticalSpacing(7)
        self.phase_grid.setColumnStretch(0, 1)
        payments.body.addWidget(holder)
        grid.addWidget(payments, 1, 0, 1, 2)

        ind = Card("Indicators")
        self.ind = KeyValues()
        for key, text in [("apr", "APR of main loan (TAEG)"), ("usury", "Usury rate (taux d'usure)"),
                          ("debt", "Debt ratio (taux d'endettement)"), ("left", "Left to live on / month"),
                          ("end", "Last payment")]:
            self.ind.add(key, text)
        ind.body.addWidget(self.ind)
        ind.body.addWidget(label(f"Banks follow the HCSF {core.MAX_DEBT_RATIO:.0f} % debt-ratio limit.",
                                 "caption", wrap=True))
        ind.body.addStretch()
        grid.addWidget(ind, 2, 0)

        self.prepay_card = Card("Early repayment")
        self.pp = KeyValues()
        for key, text in [("amount", "Amount repaid early"), ("penalty", "Penalty (IRA)"),
                          ("saved", "Interest + insurance saved"), ("end", "Loan now ends"),
                          ("payment", "Instalment afterwards")]:
            self.pp.add(key, text)
        self.pp.separator()
        self.pp.add("net", "Net saving", strong=True)
        self.prepay_card.body.addWidget(self.pp)
        self.prepay_card.body.addStretch()
        grid.addWidget(self.prepay_card, 2, 1)
        grid.setRowStretch(3, 1)
        scroll.setWidget(page)
        return scroll

    def _build_table(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 12, 0, 0)
        card = Card()
        lay.addWidget(card)
        bar = QHBoxLayout()
        self.view_loan = Segmented(LOAN_VIEWS)
        self.view_period = Segmented(["Yearly", "Monthly"])
        export = QPushButton("Export CSV…")
        export.clicked.connect(self._export)
        bar.addWidget(self.view_loan)
        bar.addWidget(self.view_period)
        bar.addStretch()
        bar.addWidget(export)
        card.body.addLayout(bar)
        self.view_loan.changed.connect(self._fill_table)
        self.view_period.changed.connect(self._fill_table)

        self.model = ScheduleModel()
        view = QTableView()
        view.setModel(self.model)
        view.setAlternatingRowColors(True)
        view.setShowGrid(False)
        view.verticalHeader().hide()
        view.verticalHeader().setDefaultSectionSize(28)
        view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        card.body.addWidget(view)
        return page

    # ---- computation

    def _project(self) -> Project:
        ins_on_balance = key_for(INSURANCE_BASE_LABELS, self.ins_base.currentText())
        prepay = self.prepay.isChecked()
        main = LoanParams(
            principal=0, annual_rate=self.rate.value(), months=round(self.years.value() * 12),
            kind=key_for(KIND_LABELS, self.kind.currentText()),
            insurance_rate=self.ins_rate.value(), insurance_on_balance=ins_on_balance,
            insurance_coverage=self.coverage.value(),
            deferral_type=key_for(DEFERRAL_LABELS, self.deferral.currentText()),
            deferral_months=int(self.deferral_months.value()),
            prepayment_month=int(self.prepay_month.value()) if prepay else 0,
            prepayment_amount=self.prepay_amount.value() if prepay else 0.0,
            prepayment_mode=key_for(PREPAY_LABELS, self.prepay_mode.currentText()))
        project = Project(
            works_cost=self.works.value(), main=main, down_payment=self.down.value(),
            grants=self.grants.value(), application_fee=self.app_fee.value(),
            guarantee_fee=self.guarantee.value(), broker_fee=self.broker.value(),
            monthly_income=self.income.value(), existing_debt=self.existing.value(),
            usury_rate=None if self.usury_auto.isChecked() else self.usury.value())
        if self.eco.isChecked():
            _, cap, max_years = core.ECO_PTZ_CATEGORIES[self.eco_cat.currentIndex()]
            project.eco_ptz = LoanParams(
                principal=self.eco_amount.value(), annual_rate=0.0, months=round(self.eco_years.value() * 12),
                kind=core.ECO_PTZ, insurance_rate=self.ins_rate.value() if self.eco_ins.isChecked() else 0.0,
                insurance_on_balance=ins_on_balance, insurance_coverage=self.coverage.value())
            project.eco_ptz_cap, project.eco_ptz_max_months = cap, max_years * 12
        return project

    def recalculate(self) -> None:
        project = self._project()
        try:
            sim = simulate(project)
        except ValueError as exc:
            self.alert.show_messages([str(exc).capitalize() + "."])
            return
        self.sim = sim
        over = sim.apr is not None and sim.usury_rate is not None and sim.apr > sim.usury_rate
        self.k_monthly.set(eur(sim.max_monthly), "Insurance included, all loans")
        self.k_cost.set(eur(sim.total_cost, 0), "Interest, insurance, fees and penalties")
        self.k_apr.set(pct(sim.apr), f"Legal maximum (usure): {pct(sim.usury_rate)}", "bad" if over else None)
        self.k_debt.show(sim)
        self.alert.show_messages(sim.warnings, "APR below the usury rate and debt ratio within limits.")

        self.plan.set("works", eur(project.works_cost))
        self.plan.set("down", eur(project.down_payment))
        self.plan.set("grants", eur(project.grants))
        self.plan.set("to_finance", eur(max(sim.amount_to_finance, 0)))
        self.plan.set("main", eur(sim.main.principal if sim.main else 0))
        self.plan.set("eco", eur(sim.eco.principal if sim.eco else 0))

        self.cost.set("interest", eur(sim.total_interest))
        self.cost.set("insurance", eur(sim.total_insurance))
        self.cost.set("fees", eur(sim.fees))
        self.cost.set("penalty", eur(sim.total_penalty))
        self.cost.set("total", eur(sim.total_cost))
        self.cost.set("repaid", eur(sum(s.total_paid for s in sim.schedules) + sim.fees))

        self.ind.set("apr", pct(sim.apr), "bad" if over else None)
        self.ind.set("usury", pct(sim.usury_rate))
        self.ind.set("debt", pct(sim.debt_ratio), self.k_debt.value.property("tone") or None)
        self.ind.set("left", eur(sim.remaining_income) if sim.remaining_income is not None else "—")
        n = len(sim.combined)
        self.ind.set("end", f"month {n} ({n / 12:.1f} years)" if n else "—")

        self._fill_phases(sim)
        self._fill_prepayment(sim)
        self._fill_table()
        self.charts.plot(sim)

    def _fill_phases(self, sim: core.Simulation) -> None:
        while self.phase_grid.count():
            self.phase_grid.takeAt(0).widget().setParent(None)
        headers = ["Period", "Instalment", "Insurance", "Total / month"]
        for col, text in enumerate(headers):
            lbl = label(text, "caption")
            if col:
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.phase_grid.addWidget(lbl, 0, col)
        for row, ph in enumerate(core.phases(sim.combined), 1):
            span = f"Month {ph.start}" if ph.start == ph.end else f"Months {ph.start} – {ph.end}"
            ins = eur(ph.avg_insurance) + (" avg" if ph.end > ph.start and ph.avg_insurance else "")
            for col, text in enumerate([span, eur(ph.payment), ins, eur(ph.total)]):
                lbl = label(text, "strong" if col == 3 else None)
                if col:
                    lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.phase_grid.addWidget(lbl, row, col)

    def _fill_prepayment(self, sim: core.Simulation) -> None:
        base, s = sim.main_baseline, sim.main
        if not s or base is s:
            self.prepay_card.hide()
            return
        self.prepay_card.show()
        prepaid = next(r for r in s.rows if r.prepayment > 0)
        saved = (base.total_interest + base.total_insurance) - (s.total_interest + s.total_insurance)
        net = saved - s.prepayment_penalty
        self.pp.set("amount", f"{eur(prepaid.prepayment)} after month {prepaid.month}")
        self.pp.set("penalty", eur(s.prepayment_penalty))
        self.pp.set("saved", eur(saved))
        self.pp.set("end", f"month {s.months} instead of {base.months}")
        after = s.rows[prepaid.month] if prepaid.month < s.months else None
        self.pp.set("payment", eur(after.payment) if after else "loan fully repaid")
        self.pp.set("net", eur(net), "good" if net > 0 else "bad")

    def _view_rows(self) -> list[Row]:
        sim = self.sim
        if not sim:
            return []
        source = [sim.combined, sim.main.rows if sim.main else [],
                  sim.eco.rows if sim.eco else []][self.view_loan.index()]
        return core.yearly(source) if self.view_period.index() == 0 else source

    def _fill_table(self, *_):
        self.model.set_rows(self._view_rows(), "Year" if self.view_period.index() == 0 else "Month")

    def _export(self):
        if not self.model.rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export amortization table", "tableau_amortissement.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        # Semicolons and decimal commas so French Excel opens it directly.
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(ScheduleModel.HEADERS)
            for r in self.model.rows:
                first, *numbers = self.model.cells(r)
                writer.writerow([first, *(f"{x:.2f}".replace(".", ",") for x in numbers)])
