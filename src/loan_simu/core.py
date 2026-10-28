"""Calculation engine for French renovation loans (prêt travaux).

Conventions follow French banking practice:
- the monthly rate is the nominal annual rate / 12 (taux proportionnel);
- the APR (TAEG) is the actuarial annual rate that equates the net amount
  received with every payment due (interest, mandatory insurance, fees);
- early repayment penalties (IRA) follow the Code de la consommation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

CONSUMER = "consumer"   # prêt personnel travaux (crédit à la consommation)
MORTGAGE = "mortgage"   # prêt immobilier travaux (garantie : caution / hypothèque)
ECO_PTZ = "eco_ptz"     # éco-prêt à taux zéro

DEFERRAL_NONE = "none"
DEFERRAL_PARTIAL = "partial"  # différé partiel : only interest + insurance are paid
DEFERRAL_TOTAL = "total"      # différé total : interest is capitalised

REDUCE_DURATION = "duration"
REDUCE_PAYMENT = "payment"

MAX_DEBT_RATIO = 35.0            # HCSF recommendation, insurance included
MAX_MORTGAGE_MONTHS = 25 * 12    # HCSF recommendation
CONSUMER_LOAN_CEILING = 75_000   # above this, a renovation loan is a real-estate credit
CONSUMER_IRA_THRESHOLD = 10_000  # no penalty below this amount repaid over 12 months

# Taux d'usure published quarterly by the Banque de France. Update every quarter.
USURY_PERIOD = "Q4 2026 (real-estate) / Q3 2026 (consumer)"
USURY_MORTGAGE = [(120, 4.09), (240, 4.68), (None, 5.40)]     # (duration < months, rate)
USURY_CONSUMER = [(3_000, 23.52), (6_000, 15.67), (None, 8.56)]  # (amount <= €, rate)

# Éco-PTZ categories: (label, maximum amount, maximum duration in years).
ECO_PTZ_CATEGORIES = [
    ("1 action – windows only", 7_000, 15),
    ("1 action", 15_000, 15),
    ("2 actions", 25_000, 15),
    ("3 actions or more", 30_000, 15),
    ("Global energy performance", 50_000, 20),
    ("With MaPrimeRénov' (rénovation d'ampleur)", 50_000, 20),
    ("Non-collective sanitation (ANC)", 10_000, 15),
]


@dataclass
class LoanParams:
    principal: float
    annual_rate: float                  # nominal, in %
    months: int
    kind: str = CONSUMER
    insurance_rate: float = 0.0         # annual, in % of the insured capital
    insurance_on_balance: bool = False  # False: on initial capital, True: on remaining capital
    insurance_coverage: float = 100.0   # quotité, in % (200 for two borrowers fully covered)
    deferral_type: str = DEFERRAL_NONE
    deferral_months: int = 0
    prepayment_month: int = 0
    prepayment_amount: float = 0.0
    prepayment_mode: str = REDUCE_DURATION


@dataclass
class Row:
    month: int
    payment: float      # scheduled instalment (principal + interest), insurance excluded
    interest: float
    principal: float
    insurance: float
    prepayment: float
    balance: float      # remaining capital after this month

    @property
    def total(self) -> float:
        return self.payment + self.insurance + self.prepayment


@dataclass
class Schedule:
    principal: float
    rows: list[Row]
    prepayment_penalty: float = 0.0

    @property
    def months(self) -> int:
        return len(self.rows)

    @property
    def total_interest(self) -> float:
        # Computed from cash flows so capitalised interest (total deferral) is counted once.
        return sum(r.payment + r.prepayment for r in self.rows) - self.principal

    @property
    def total_insurance(self) -> float:
        return sum(r.insurance for r in self.rows)

    @property
    def total_paid(self) -> float:
        return sum(r.total for r in self.rows) + self.prepayment_penalty

    @property
    def regular_payment(self) -> float:
        for r in self.rows:
            if r.principal > 0:
                return r.payment
        return 0.0


def annuity(principal: float, monthly_rate: float, months: int) -> float:
    if months <= 0:
        raise ValueError("duration must be positive")
    if monthly_rate == 0:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -months)


def prepayment_penalty(kind: str, amount: float, balance_before: float, monthly_rate: float,
                       remaining_months: int, payment: float) -> float:
    """Indemnité de remboursement anticipé (IRA)."""
    if kind == MORTGAGE:
        # min(6 months of interest on the amount repaid, 3 % of the remaining capital)
        return min(6 * amount * monthly_rate, 0.03 * balance_before)
    if kind == CONSUMER:
        if amount <= CONSUMER_IRA_THRESHOLD:
            return 0.0
        pct = 0.01 if remaining_months > 12 else 0.005
        # Capped at the interest that would still have been paid.
        cap = max(payment * remaining_months - balance_before, 0.0)
        return min(pct * amount, cap)
    return 0.0


def amortize(p: LoanParams) -> Schedule:
    if p.principal <= 0:
        raise ValueError("loan amount must be positive")
    if p.months <= 0:
        raise ValueError("duration must be positive")
    r = p.annual_rate / 100 / 12
    insurance_rate = p.insurance_rate / 100 / 12 * p.insurance_coverage / 100
    deferral = p.deferral_months if p.deferral_type != DEFERRAL_NONE else 0
    if deferral >= p.months:
        raise ValueError("the deferral must be shorter than the loan")

    def insurance(balance: float) -> float:
        return (balance if p.insurance_on_balance else p.principal) * insurance_rate

    balance = p.principal
    rows: list[Row] = []
    for month in range(1, deferral + 1):
        interest = balance * r
        ins = insurance(balance)
        if p.deferral_type == DEFERRAL_TOTAL:
            balance += interest
            rows.append(Row(month, 0.0, interest, 0.0, ins, 0.0, balance))
        else:
            rows.append(Row(month, interest, interest, 0.0, ins, 0.0, balance))

    payment = annuity(balance, r, p.months - deferral)
    penalty = 0.0
    month = deferral
    while balance > 0.005:
        month += 1
        ins = insurance(balance)
        interest = balance * r
        principal = payment - interest
        if principal >= balance - 0.005 or month >= p.months:
            principal = balance
        balance -= principal
        prepay = 0.0
        if month == p.prepayment_month and p.prepayment_amount > 0 and balance > 0.005:
            prepay = min(p.prepayment_amount, balance)
            penalty = prepayment_penalty(p.kind, prepay, balance, r, p.months - month, payment)
            balance -= prepay
            if p.prepayment_mode == REDUCE_PAYMENT and balance > 0.005:
                payment = annuity(balance, r, p.months - month)
        rows.append(Row(month, principal + interest, interest, principal, ins, prepay, max(balance, 0.0)))
    return Schedule(p.principal, rows, penalty)


def apr(net_amount: float, outflows: list[float]) -> float | None:
    """Actuarial annual rate (TAEG), in %, for monthly outflows starting at month 1."""
    if net_amount <= 0 or not outflows:
        return None

    def present_value(rate: float) -> float:
        return sum(cf / (1 + rate) ** k for k, cf in enumerate(outflows, 1))

    if present_value(0.0) <= net_amount:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if present_value(mid) > net_amount:
            lo = mid
        else:
            hi = mid
    return ((1 + lo) ** 12 - 1) * 100


def usury_rate(kind: str, months: int, amount: float) -> float | None:
    if kind == MORTGAGE:
        for limit, rate in USURY_MORTGAGE:
            if limit is None or months < limit:
                return rate
    if kind == CONSUMER:
        for limit, rate in USURY_CONSUMER:
            if limit is None or amount <= limit:
                return rate
    return None


def combine(schedules: list[Schedule]) -> list[Row]:
    by_month: dict[int, Row] = {}
    for s in schedules:
        for r in s.rows:
            acc = by_month.setdefault(r.month, Row(r.month, 0, 0, 0, 0, 0, 0))
            acc.payment += r.payment
            acc.interest += r.interest
            acc.principal += r.principal
            acc.insurance += r.insurance
            acc.prepayment += r.prepayment
    # A loan that has ended still contributes 0 to the balance; recompute it month by month.
    for m, acc in by_month.items():
        acc.balance = sum(_balance_at(s, m) for s in schedules)
    return [by_month[m] for m in sorted(by_month)]


def _balance_at(s: Schedule, month: int) -> float:
    if month <= s.months:
        return s.rows[month - 1].balance
    return 0.0


def yearly(rows: list[Row]) -> list[Row]:
    years: dict[int, Row] = {}
    for r in rows:
        y = (r.month - 1) // 12 + 1
        acc = years.setdefault(y, Row(y, 0, 0, 0, 0, 0, 0))
        acc.payment += r.payment
        acc.interest += r.interest
        acc.principal += r.principal
        acc.insurance += r.insurance
        acc.prepayment += r.prepayment
        acc.balance = r.balance
    return [years[y] for y in sorted(years)]


@dataclass
class Phase:
    start: int
    end: int
    payment: float          # principal + interest
    avg_insurance: float

    @property
    def total(self) -> float:
        return self.payment + self.avg_insurance


def phases(rows: list[Row], tolerance: float = 0.5) -> list[Phase]:
    """Group consecutive months that share the same instalment."""
    result: list[Phase] = []
    ins_sum = 0.0
    for r in rows:
        last = result[-1] if result else None
        if last and abs(r.payment - last.payment) <= tolerance:
            last.end = r.month
            ins_sum += r.insurance
            last.avg_insurance = ins_sum / (last.end - last.start + 1)
        else:
            result.append(Phase(r.month, r.month, r.payment, r.insurance))
            ins_sum = r.insurance
    return result


@dataclass
class Project:
    works_cost: float
    main: LoanParams                     # principal is computed by simulate()
    down_payment: float = 0.0
    grants: float = 0.0                  # MaPrimeRénov', CEE, local aid...
    eco_ptz: LoanParams | None = None
    eco_ptz_cap: float | None = None
    eco_ptz_max_months: int | None = None
    application_fee: float = 0.0         # frais de dossier
    guarantee_fee: float = 0.0           # caution / hypothèque
    broker_fee: float = 0.0              # frais de courtage
    monthly_income: float = 0.0
    existing_debt: float = 0.0           # other monthly loan payments
    usury_rate: float | None = None      # None: use the built-in table


@dataclass
class Simulation:
    amount_to_finance: float
    main: Schedule | None = None
    main_baseline: Schedule | None = None  # main loan without early repayment
    eco: Schedule | None = None
    combined: list[Row] = field(default_factory=list)
    fees: float = 0.0
    apr: float | None = None
    usury_rate: float | None = None
    max_monthly: float = 0.0
    debt_ratio: float | None = None
    remaining_income: float | None = None  # reste à vivre
    warnings: list[str] = field(default_factory=list)

    @property
    def schedules(self) -> list[Schedule]:
        return [s for s in (self.main, self.eco) if s]

    @property
    def total_interest(self) -> float:
        return sum(s.total_interest for s in self.schedules)

    @property
    def total_insurance(self) -> float:
        return sum(s.total_insurance for s in self.schedules)

    @property
    def total_penalty(self) -> float:
        return sum(s.prepayment_penalty for s in self.schedules)

    @property
    def total_cost(self) -> float:
        return self.total_interest + self.total_insurance + self.fees + self.total_penalty

    @property
    def total_borrowed(self) -> float:
        return sum(s.principal for s in self.schedules)


def simulate(project: Project) -> Simulation:
    to_finance = project.works_cost - project.down_payment - project.grants
    sim = Simulation(amount_to_finance=to_finance)
    if to_finance <= 0:
        sim.warnings.append("Nothing to borrow: the down payment and grants cover the works.")
        return sim

    eco_amount = 0.0
    if project.eco_ptz and project.eco_ptz.principal > 0:
        eco = replace(project.eco_ptz, annual_rate=0.0, kind=ECO_PTZ)
        if eco.principal > to_finance:
            sim.warnings.append("The éco-PTZ exceeds the amount to finance; it has been reduced.")
            eco = replace(eco, principal=to_finance)
        if project.eco_ptz_cap is not None and eco.principal > project.eco_ptz_cap:
            sim.warnings.append(f"The éco-PTZ for this category is capped at {project.eco_ptz_cap:,.0f} €.")
        if project.eco_ptz_max_months is not None and eco.months > project.eco_ptz_max_months:
            sim.warnings.append(
                f"The éco-PTZ for this category cannot exceed {project.eco_ptz_max_months // 12} years.")
        sim.eco = amortize(eco)
        eco_amount = eco.principal

    main_amount = to_finance - eco_amount
    if main_amount > 0.005:
        main = replace(project.main, principal=main_amount)
        deferral = main.deferral_months if main.deferral_type != DEFERRAL_NONE else 0
        if main.prepayment_amount > 0 and not deferral < main.prepayment_month <= main.months:
            sim.warnings.append("Early repayment ignored: its month must fall after the deferral "
                                "and within the loan duration.")
            main = replace(main, prepayment_amount=0.0)
        sim.main = amortize(main)
        sim.main_baseline = amortize(replace(main, prepayment_amount=0.0)) \
            if main.prepayment_amount > 0 else sim.main

        sim.fees = project.application_fee + project.guarantee_fee + project.broker_fee
        sim.apr = apr(main_amount - sim.fees, [r.payment + r.insurance for r in sim.main_baseline.rows])
        sim.usury_rate = (project.usury_rate if project.usury_rate is not None
                          else usury_rate(main.kind, main.months, main_amount))
        if sim.apr is not None and sim.usury_rate is not None and sim.apr > sim.usury_rate:
            sim.warnings.append(
                f"APR {sim.apr:.2f} % exceeds the usury rate {sim.usury_rate:.2f} %: "
                "a bank cannot legally grant this loan.")
        if main.kind == CONSUMER and main_amount > CONSUMER_LOAN_CEILING:
            sim.warnings.append("Above 75 000 €, a renovation loan falls under real-estate credit rules: "
                                "choose the real-estate loan type.")
        if main.kind == MORTGAGE and main.months > MAX_MORTGAGE_MONTHS:
            sim.warnings.append("The HCSF limits real-estate loans to 25 years.")

    sim.combined = combine(sim.schedules)
    sim.max_monthly = max((r.payment + r.insurance for r in sim.combined), default=0.0)
    if project.monthly_income > 0:
        sim.debt_ratio = (sim.max_monthly + project.existing_debt) / project.monthly_income * 100
        sim.remaining_income = project.monthly_income - project.existing_debt - sim.max_monthly
        if sim.debt_ratio > MAX_DEBT_RATIO:
            sim.warnings.append(f"Debt ratio {sim.debt_ratio:.1f} % is above the {MAX_DEBT_RATIO:.0f} % "
                                "HCSF limit: banks will likely refuse.")
    return sim
