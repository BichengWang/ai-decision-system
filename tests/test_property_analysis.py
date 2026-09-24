from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from src.fin.house.target_market_analysis import (
    PropertyAssumptions,
    calculate_metrics,
    ltv_grid,
    main,
    optimize_ltv,
)


class PropertyAnalysisTests(unittest.TestCase):
    def test_notebook_defaults_reproduce_expected_financials(self) -> None:
        metrics = calculate_metrics(PropertyAssumptions(), 0.5)

        self.assertAlmostEqual(metrics.gross_rental_income, 43_200)
        self.assertAlmostEqual(metrics.effective_rental_income, 41_040)
        self.assertAlmostEqual(metrics.operating_expenses, 19_133.2)
        self.assertAlmostEqual(metrics.net_operating_income, 21_906.8)
        self.assertAlmostEqual(metrics.annual_debt_service, 20_500)
        self.assertAlmostEqual(metrics.cash_flow_before_tax, 1_406.8)
        self.assertAlmostEqual(metrics.total_return, 26_006.8)
        self.assertAlmostEqual(metrics.roe_percent, 6.3431219512)

    def test_unconstrained_optimum_uses_upper_boundary(self) -> None:
        optimum = optimize_ltv(PropertyAssumptions(), max_ltv=0.8)
        self.assertEqual(optimum.ltv, 0.8)
        self.assertLess(optimum.cash_flow_before_tax, 0)

    def test_cash_flow_constraint_finds_exact_feasible_boundary(self) -> None:
        assumptions = PropertyAssumptions()
        optimum = optimize_ltv(
            assumptions,
            max_ltv=0.8,
            require_nonnegative_cash_flow=True,
        )
        expected_ltv = 21_906.8 / (820_000 * 0.05)
        self.assertAlmostEqual(optimum.ltv, expected_ltv)
        self.assertAlmostEqual(optimum.cash_flow_before_tax, 0, places=9)

    def test_expensive_debt_selects_no_leverage(self) -> None:
        assumptions = PropertyAssumptions(
            annual_appreciation_rate=0,
            annual_interest_rate=0.1,
        )
        self.assertEqual(optimize_ltv(assumptions, max_ltv=0.8).ltv, 0)

    def test_equal_borrowing_cost_selects_lower_leverage(self) -> None:
        assumptions = PropertyAssumptions()
        unlevered_return = calculate_metrics(assumptions, 0).return_on_equity
        assumptions = PropertyAssumptions(annual_interest_rate=unlevered_return)
        self.assertEqual(optimize_ltv(assumptions, min_ltv=0.2, max_ltv=0.8).ltv, 0.2)

    def test_grid_includes_non_multiple_upper_bound(self) -> None:
        self.assertEqual(ltv_grid(0.25, 0.1), [0.0, 0.1, 0.2, 0.25])

    def test_invalid_assumptions_and_bounds_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "property_value"):
            PropertyAssumptions(property_value=0)
        with self.assertRaisesRegex(ValueError, "vacancy_rate"):
            PropertyAssumptions(vacancy_rate=5)
        with self.assertRaisesRegex(ValueError, "less than 1"):
            calculate_metrics(PropertyAssumptions(), 1)
        with self.assertRaisesRegex(ValueError, "min_ltv"):
            optimize_ltv(PropertyAssumptions(), min_ltv=0.8, max_ltv=0.5)

    def test_json_cli_is_machine_readable(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(["--format", "json", "--max-ltv", "0.2", "--grid-step", "0.1"]),
                0,
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(len(payload["scenarios"]), 3)
        self.assertEqual(payload["optimum"]["ltv"], 0.2)
        self.assertIsNone(payload["scenarios"][0]["debt_service_coverage_ratio"])


if __name__ == "__main__":
    unittest.main()
