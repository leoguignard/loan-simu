import unittest

from loan_simu.core import (
    CONSUMER, DEFERRAL_PARTIAL, DEFERRAL_TOTAL, MORTGAGE, REDUCE_DURATION, REDUCE_PAYMENT,
    LoanParams, Project, amortize, annuity, apr, phases, prepayment_penalty, simulate, usury_rate,
    yearly,
)


class AnnuityTest(unittest.TestCase):
    def test_known_value(self):
        # 100 000 € at 3 % over 20 years
        self.assertAlmostEqual(annuity(100_000, 0.03 / 12, 240), 554.60, places=2)

    def test_zero_rate(self):
        self.assertAlmostEqual(annuity(12_000, 0, 120), 100)


class AmortizeTest(unittest.TestCase):
    def test_principal_fully_repaid(self):
        s = amortize(LoanParams(30_000, 4.5, 84))
        self.assertEqual(s.months, 84)
        self.assertAlmostEqual(sum(r.principal for r in s.rows), 30_000, places=6)
        self.assertAlmostEqual(s.rows[-1].balance, 0, places=6)
        self.assertAlmostEqual(s.total_interest, sum(r.interest for r in s.rows), places=6)

    def test_insurance_on_initial_capital(self):
        s = amortize(LoanParams(30_000, 4.5, 84, insurance_rate=0.36))
        self.assertTrue(all(abs(r.insurance - 9.0) < 1e-9 for r in s.rows))

    def test_insurance_on_balance_decreases(self):
        s = amortize(LoanParams(30_000, 4.5, 84, insurance_rate=0.36, insurance_on_balance=True,
                                insurance_coverage=200))
        self.assertAlmostEqual(s.rows[0].insurance, 18.0)
        self.assertLess(s.rows[-1].insurance, 1)

    def test_partial_deferral(self):
        s = amortize(LoanParams(12_000, 6, 24, deferral_type=DEFERRAL_PARTIAL, deferral_months=6))
        self.assertAlmostEqual(s.rows[0].payment, 60)
        self.assertEqual(s.rows[5].balance, 12_000)
        self.assertAlmostEqual(s.rows[6].payment, annuity(12_000, 0.005, 18), places=6)

    def test_total_deferral_capitalises_interest(self):
        s = amortize(LoanParams(12_000, 6, 24, deferral_type=DEFERRAL_TOTAL, deferral_months=6))
        self.assertEqual(s.rows[0].payment, 0)
        self.assertAlmostEqual(s.rows[5].balance, 12_000 * 1.005 ** 6, places=6)
        self.assertAlmostEqual(s.total_interest, sum(r.interest for r in s.rows), places=6)

    def test_prepayment_reduces_duration(self):
        base = amortize(LoanParams(50_000, 4, 120, kind=MORTGAGE))
        s = amortize(LoanParams(50_000, 4, 120, kind=MORTGAGE, prepayment_month=24,
                                prepayment_amount=10_000, prepayment_mode=REDUCE_DURATION))
        self.assertLess(s.months, 120)
        self.assertLess(s.total_interest, base.total_interest)
        self.assertAlmostEqual(s.prepayment_penalty, 6 * 10_000 * 0.04 / 12)

    def test_prepayment_reduces_payment(self):
        s = amortize(LoanParams(50_000, 4, 120, prepayment_month=24, prepayment_amount=10_000,
                                prepayment_mode=REDUCE_PAYMENT))
        self.assertEqual(s.months, 120)
        self.assertLess(s.rows[30].payment, s.rows[0].payment)

    def test_full_prepayment(self):
        s = amortize(LoanParams(20_000, 5, 60, prepayment_month=12, prepayment_amount=1e9))
        self.assertEqual(s.months, 12)
        self.assertAlmostEqual(s.rows[-1].balance, 0)


class PenaltyTest(unittest.TestCase):
    def test_mortgage_capped_at_3_percent(self):
        self.assertAlmostEqual(prepayment_penalty(MORTGAGE, 100_000, 100_000, 0.08 / 12, 100, 0), 3_000)

    def test_consumer_threshold(self):
        self.assertEqual(prepayment_penalty(CONSUMER, 10_000, 20_000, 0.004, 48, 500), 0)
        self.assertAlmostEqual(prepayment_penalty(CONSUMER, 15_000, 20_000, 0.004, 48, 500), 150)
        self.assertAlmostEqual(prepayment_penalty(CONSUMER, 15_000, 20_000, 0.004, 12, 1_700), 75)


class AprTest(unittest.TestCase):
    def test_no_fees_is_actuarial_equivalent(self):
        s = amortize(LoanParams(30_000, 4.5, 84))
        expected = ((1 + 0.045 / 12) ** 12 - 1) * 100
        self.assertAlmostEqual(apr(30_000, [r.payment for r in s.rows]), expected, places=6)

    def test_fees_and_insurance_raise_apr(self):
        s = amortize(LoanParams(30_000, 4.5, 84, insurance_rate=0.3))
        self.assertGreater(apr(29_500, [r.payment + r.insurance for r in s.rows]), 5.0)

    def test_zero_rate(self):
        self.assertEqual(apr(1_000, [100] * 10), 0.0)


class SimulateTest(unittest.TestCase):
    def test_financing_plan_with_eco_ptz(self):
        sim = simulate(Project(
            works_cost=60_000, down_payment=5_000, grants=10_000,
            main=LoanParams(0, 4.5, 120, insurance_rate=0.3),
            eco_ptz=LoanParams(15_000, 0, 180),
            application_fee=500, monthly_income=4_000))
        self.assertEqual(sim.amount_to_finance, 45_000)
        self.assertEqual(sim.main.principal, 30_000)
        self.assertEqual(sim.eco.principal, 15_000)
        self.assertAlmostEqual(sim.eco.total_interest, 0, places=6)
        self.assertEqual(len(sim.combined), 180)
        self.assertAlmostEqual(sim.combined[0].balance, sim.main.rows[0].balance + sim.eco.rows[0].balance)
        self.assertAlmostEqual(sim.combined[150].balance, sim.eco.rows[150].balance)
        self.assertGreater(sim.apr, 4.5)
        self.assertEqual(len(phases(sim.combined)), 2)

    def test_warnings(self):
        sim = simulate(Project(works_cost=100_000, main=LoanParams(0, 12, 60, kind=CONSUMER),
                               monthly_income=2_000))
        text = " ".join(sim.warnings)
        self.assertIn("usury", text)
        self.assertIn("75 000", text)
        self.assertIn("Debt ratio", text)

    def test_nothing_to_finance(self):
        sim = simulate(Project(works_cost=10_000, down_payment=10_000, main=LoanParams(0, 4, 60)))
        self.assertIsNone(sim.main)
        self.assertTrue(sim.warnings)

    def test_usury_brackets(self):
        self.assertEqual(usury_rate(MORTGAGE, 119, 0), 4.09)
        self.assertEqual(usury_rate(MORTGAGE, 240, 0), 5.40)
        self.assertEqual(usury_rate(CONSUMER, 0, 3_000), 23.52)
        self.assertEqual(usury_rate(CONSUMER, 0, 30_000), 8.56)

    def test_yearly(self):
        s = amortize(LoanParams(30_000, 4.5, 84))
        years = yearly(s.rows)
        self.assertEqual(len(years), 7)
        self.assertAlmostEqual(sum(y.principal for y in years), 30_000, places=6)


if __name__ == "__main__":
    unittest.main()
