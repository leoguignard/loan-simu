"""Matplotlib charts embedded in Qt, coloured from the current theme."""
from __future__ import annotations

import matplotlib

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .. import core  # noqa: E402
from . import theme  # noqa: E402
from .widgets import eur  # noqa: E402

K_EUR = FuncFormatter(lambda v, _: f"{v / 1000:.0f} k€")


class Chart(FigureCanvasQTAgg):
    def __init__(self, width: float, height: float):
        self.fig = Figure(figsize=(width, height), dpi=100, layout="constrained")
        super().__init__(self.fig)
        self.setStyleSheet("background: transparent;")

    def begin(self) -> theme.Palette:
        p = theme.current()
        self.fig.clear()
        self.fig.set_facecolor(p.surface)
        return p

    @staticmethod
    def style_axes(ax, p: theme.Palette) -> None:
        ax.set_facecolor(p.surface)
        ax.tick_params(colors=p.muted, labelsize=8, length=0)
        for name, spine in ax.spines.items():
            spine.set_visible(name == "bottom")
            spine.set_color(p.border)
        ax.grid(axis="y", color=p.border, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.xaxis.label.set_color(p.muted)


class Donut(Chart):
    def __init__(self):
        super().__init__(2.6, 2.6)

    def plot(self, s: core.Schedule | None) -> None:
        p = self.begin()
        if s:
            ax = self.fig.add_subplot(111)
            parts = [(s.principal, "Capital", p.principal), (s.total_interest, "Interest", p.interest),
                     (s.total_insurance, "Insurance", p.insurance)]
            parts = [x for x in parts if x[0] > 0.005]
            ax.pie([x[0] for x in parts], colors=[x[2] for x in parts], startangle=90, counterclock=False,
                   wedgeprops=dict(width=0.32, edgecolor=p.surface, linewidth=2))
            ax.text(0, 0.08, eur(s.total_paid, 0), ha="center", va="center", color=p.text, fontsize=11,
                    fontweight="bold")
            ax.text(0, -0.16, "repaid in total", ha="center", va="center", color=p.muted, fontsize=8)
        self.draw_idle()


class ScheduleCharts(Chart):
    def __init__(self):
        super().__init__(7, 5)

    def plot(self, sim: core.Simulation | None) -> None:
        p = self.begin()
        if not sim or not sim.combined:
            self.draw_idle()
            return
        years = core.yearly(sim.combined)
        x = [y.month for y in years]
        principal = [y.principal + y.prepayment for y in years]
        interest = [y.payment - y.principal for y in years]  # paid, not capitalised
        insurance = [y.insurance for y in years]

        ax = self.fig.add_subplot(211)
        ax.bar(x, principal, color=p.principal, label="Capital", width=0.7)
        ax.bar(x, interest, bottom=principal, color=p.interest, label="Interest", width=0.7)
        ax.bar(x, insurance, bottom=[a + b for a, b in zip(principal, interest)], color=p.insurance,
               label="Insurance", width=0.7)
        ax.set_title("What you pay each year", fontsize=10, loc="left", fontweight="bold", color=p.text)
        ax.set_xlabel("Year", fontsize=8)
        ax.yaxis.set_major_formatter(K_EUR)
        ax.legend(frameon=False, fontsize=8, labelcolor=p.text, ncol=3, loc="upper right")
        self.style_axes(ax, p)

        ax = self.fig.add_subplot(212)
        if sim.main:
            ax.fill_between([r.month / 12 for r in sim.main.rows], [r.balance for r in sim.main.rows],
                            color=p.principal, alpha=0.18, linewidth=0)
            ax.plot([r.month / 12 for r in sim.main.rows], [r.balance for r in sim.main.rows],
                    color=p.principal, label="Main loan", linewidth=2)
        if sim.eco:
            ax.plot([r.month / 12 for r in sim.eco.rows], [r.balance for r in sim.eco.rows],
                    color=p.eco, label="Éco-PTZ", linewidth=2)
        if sim.main and sim.eco:
            ax.plot([r.month / 12 for r in sim.combined], [r.balance for r in sim.combined],
                    color=p.muted, linestyle="--", linewidth=1.2, label="Total")
        ax.set_title("Remaining capital", fontsize=10, loc="left", fontweight="bold", color=p.text)
        ax.set_xlabel("Years", fontsize=8)
        ax.set_ylim(bottom=0)
        ax.set_xlim(left=0)
        ax.yaxis.set_major_formatter(K_EUR)
        ax.legend(frameon=False, fontsize=8, labelcolor=p.text)
        self.style_axes(ax, p)
        self.draw_idle()
