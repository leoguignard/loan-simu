# Renovation Loan Simulator (France)

A desktop app (Qt / PySide6) to simulate a loan for renovating an apartment in France (*prêt travaux*).

```bash
pip install .            # or `pip install -e .` while developing
loan-simu                # or: python -m loan_simu
python -m unittest       # engine + UI smoke tests (needs the package installed, e.g. with -e)
```

```text
src/loan_simu/
  core.py         calculation engine (no GUI dependency)
  ui/
    app.py        main window and entry point
    simple.py     simple mode
    advanced.py   in-depth mode
    widgets.py    cards, number fields, debt-ratio gauge
    charts.py     matplotlib charts
    theme.py      light/dark palettes and stylesheet
tests/            engine tests and an offscreen UI smoke test
```

Numbers are shown in French format and you can type `4,5` or `4.5`. Results update as you type.

The app follows the system's light or dark mode. To force one, set `LOAN_SIMU_THEME=light` or `LOAN_SIMU_THEME=dark`.

## Simple mode

You enter the works cost, down payment, duration, rate, insurance, your net monthly income and your other loan payments. You get:

- the monthly payment, the total cost of credit and the APR (TAEG)
- the debt ratio (*taux d'endettement*), on a gauge against the 35 % HCSF limit, and the money left each month
- a breakdown of capital, interest and insurance
- a table comparing durations from 3 to 25 years, with the debt ratio for each; click a row to use that duration

## In-depth mode

| Area | What it covers |
|---|---|
| Project | Works cost, down payment (*apport*), grants (MaPrimeRénov', CEE…) |
| Main loan | Personal loan (*crédit conso*) or real-estate loan (*prêt immobilier*), rate, duration, partial or total deferral (*différé*) |
| Insurance | Rate, based on initial or remaining capital, coverage (*quotité*) |
| Fees | Bank fee (*frais de dossier*), guarantee (*caution* / *hypothèque*), broker fee |
| Éco-PTZ | 0 % loan for energy renovation, with a cap and maximum duration per category |
| Budget | Debt ratio against the 35 % HCSF limit, money left to live on (*reste à vivre*) |
| Early repayment | Penalty (IRA), interest saved, choice between a shorter loan and a lower payment |
| Checks | APR above the usury rate, consumer loan over 75 000 €, real-estate loan over 25 years |

The in-depth mode also has an amortization table (combined or per loan, by month or by year, exported as CSV for French Excel) and charts.

## Calculation rules

- Monthly rate = nominal rate / 12 (*taux proportionnel*), constant monthly payments.
- The TAEG is the actuarial rate including interest, insurance and upfront fees. It is calculated without the early repayment, as banks do.
- IRA:
  - real-estate loan: the lower of 6 months of interest and 3 % of the remaining capital
  - consumer loan: 1 % of the amount repaid (0.5 % if 12 months or less remain), nothing for 10 000 € or less, capped at the remaining interest
  - éco-PTZ: no penalty

## Keep these up to date

The values in [src/loan_simu/core.py](src/loan_simu/core.py) change over time:

- **Usury rates** (`USURY_*`) are published every quarter by the Banque de France. The real-estate table is from Q4 2026. The consumer table is from Q3 2026, because the Q4 figures were not found.
- **Éco-PTZ caps** (`ECO_PTZ_CATEGORIES`): check them on service-public.fr (page F19905).

This is a simulation, not a loan offer. Your bank's offer (*offre de prêt*) and its FISE are the documents that count.
