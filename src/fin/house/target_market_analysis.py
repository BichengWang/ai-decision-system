"""Analyze an interest-only rental property across loan-to-value ratios.

This replaces the exploratory notebook with deterministic, unit-tested finance
math. The model includes rent, vacancy, operating costs, appreciation, and
interest-only debt. It intentionally does not model amortization, income tax,
closing costs, or sale costs.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class PropertyAssumptions:
    """Annualized assumptions for one rental property."""

    property_value: float = 820_000.0
    monthly_rent: float = 3_600.0
    annual_appreciation_rate: float = 0.03
    vacancy_rate: float = 0.05
    property_tax_rate: float = 0.0125
    maintenance_rate: float = 0.005
    annual_insurance: float = 1_500.0
    management_fee_rate: float = 0.08
    annual_interest_rate: float = 0.05

    def __post_init__(self) -> None:
        _positive(self.property_value, "property_value")
        for name in ("monthly_rent", "annual_insurance"):
            _nonnegative(getattr(self, name), name)
        for name in (
            "vacancy_rate",
            "property_tax_rate",
            "maintenance_rate",
            "management_fee_rate",
            "annual_interest_rate",
        ):
            _rate(getattr(self, name), name)
        appreciation = _finite(
            self.annual_appreciation_rate, "annual_appreciation_rate"
        )
        if appreciation <= -1:
            raise ValueError("annual_appreciation_rate must be greater than -1")


@dataclass(frozen=True, slots=True)
class InvestmentMetrics:
    """One-year property metrics at a particular loan-to-value ratio."""

    ltv: float
    gross_rental_income: float
    vacancy_loss: float
    effective_rental_income: float
    operating_expenses: float
    net_operating_income: float
    loan_amount: float
    equity_investment: float
    annual_debt_service: float
    cash_flow_before_tax: float
    annual_appreciation: float
    total_return: float
    return_on_equity: float
    cap_rate: float
    debt_service_coverage_ratio: float | None

    @property
    def roe_percent(self) -> float:
        """Return on equity represented as a percentage."""
        return self.return_on_equity * 100


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return result


def _nonnegative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _rate(value: float, name: str) -> float:
    result = _finite(value, name)
    if not 0 <= result <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _ltv(value: float, name: str = "ltv") -> float:
    result = _finite(value, name)
    if not 0 <= result < 1:
        raise ValueError(f"{name} must be at least 0 and less than 1")
    return result


def calculate_metrics(
    assumptions: PropertyAssumptions,
    ltv: float,
) -> InvestmentMetrics:
    """Calculate one-year returns for an interest-only loan."""
    ratio = _ltv(ltv)
    gross_rent = assumptions.monthly_rent * 12
    vacancy_loss = gross_rent * assumptions.vacancy_rate
    effective_rent = gross_rent - vacancy_loss
    operating_expenses = (
        assumptions.property_value * assumptions.property_tax_rate
        + assumptions.property_value * assumptions.maintenance_rate
        + assumptions.annual_insurance
        + effective_rent * assumptions.management_fee_rate
    )
    noi = effective_rent - operating_expenses
    loan = assumptions.property_value * ratio
    equity = assumptions.property_value - loan
    debt_service = loan * assumptions.annual_interest_rate
    cash_flow = noi - debt_service
    appreciation = assumptions.property_value * assumptions.annual_appreciation_rate
    total_return = cash_flow + appreciation

    return InvestmentMetrics(
        ltv=ratio,
        gross_rental_income=gross_rent,
        vacancy_loss=vacancy_loss,
        effective_rental_income=effective_rent,
        operating_expenses=operating_expenses,
        net_operating_income=noi,
        loan_amount=loan,
        equity_investment=equity,
        annual_debt_service=debt_service,
        cash_flow_before_tax=cash_flow,
        annual_appreciation=appreciation,
        total_return=total_return,
        return_on_equity=total_return / equity,
        cap_rate=noi / assumptions.property_value,
        debt_service_coverage_ratio=(noi / debt_service if debt_service else None),
    )


def analyze_ltvs(
    assumptions: PropertyAssumptions,
    ltvs: Iterable[float],
) -> list[InvestmentMetrics]:
    """Calculate metrics for each supplied LTV, preserving input order."""
    return [calculate_metrics(assumptions, ratio) for ratio in ltvs]


def ltv_grid(max_ltv: float = 0.8, step: float = 0.1) -> list[float]:
    """Build an inclusive, floating-point-stable LTV grid from zero."""
    upper = _ltv(max_ltv, "max_ltv")
    increment = _positive(step, "step")
    if increment >= 1:
        raise ValueError("step must be less than 1")
    count = math.floor(upper / increment + 1e-12)
    values = [index * increment for index in range(count + 1)]
    if not math.isclose(values[-1], upper, rel_tol=0, abs_tol=1e-12):
        values.append(upper)
    return values


def optimize_ltv(
    assumptions: PropertyAssumptions,
    *,
    min_ltv: float = 0,
    max_ltv: float = 0.8,
    require_nonnegative_cash_flow: bool = False,
) -> InvestmentMetrics:
    """Find the ROE-maximizing LTV within the requested bounds.

    Under this interest-only model, ROE is a fractional linear function of LTV
    and is therefore monotonic (or constant). The optimum is at a feasible
    boundary; evaluating boundaries is exact and avoids an iterative numerical
    optimizer. Ties select the lower leverage.
    """
    lower = _ltv(min_ltv, "min_ltv")
    upper = _ltv(max_ltv, "max_ltv")
    if lower > upper:
        raise ValueError("min_ltv must not exceed max_ltv")

    if require_nonnegative_cash_flow:
        unlevered = calculate_metrics(assumptions, 0)
        if unlevered.cash_flow_before_tax < 0:
            raise ValueError("no feasible LTV has non-negative cash flow")
        if assumptions.annual_interest_rate > 0:
            cash_flow_limit = unlevered.net_operating_income / (
                assumptions.property_value * assumptions.annual_interest_rate
            )
            upper = min(upper, max(0.0, cash_flow_limit))
        if upper + 1e-12 < lower:
            raise ValueError("no LTV in the requested range has non-negative cash flow")

    lower_metrics, upper_metrics = analyze_ltvs(assumptions, (lower, upper))
    if math.isclose(
        lower_metrics.return_on_equity,
        upper_metrics.return_on_equity,
        rel_tol=1e-12,
        abs_tol=1e-15,
    ):
        return lower_metrics
    return max(
        (lower_metrics, upper_metrics), key=lambda metrics: metrics.return_on_equity
    )


def _metrics_dict(metrics: InvestmentMetrics) -> dict[str, float | None]:
    result = asdict(metrics)
    result["roe_percent"] = metrics.roe_percent
    return result


def _format_table(rows: Iterable[InvestmentMetrics]) -> str:
    header = (
        f"{'LTV':>8} {'Loan':>14} {'Equity':>14} {'NOI':>14} "
        f"{'Cash flow':>14} {'Total return':>14} {'ROE':>9}"
    )
    body = [header, "-" * len(header)]
    for item in rows:
        body.append(
            f"{item.ltv:>7.1%} "
            f"{item.loan_amount:>14,.2f} "
            f"{item.equity_investment:>14,.2f} "
            f"{item.net_operating_income:>14,.2f} "
            f"{item.cash_flow_before_tax:>14,.2f} "
            f"{item.total_return:>14,.2f} "
            f"{item.return_on_equity:>8.2%}"
        )
    return "\n".join(body)


def _parser() -> argparse.ArgumentParser:
    defaults = PropertyAssumptions()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--property-value", type=float, default=defaults.property_value)
    parser.add_argument("--monthly-rent", type=float, default=defaults.monthly_rent)
    parser.add_argument(
        "--appreciation-rate", type=float, default=defaults.annual_appreciation_rate
    )
    parser.add_argument("--vacancy-rate", type=float, default=defaults.vacancy_rate)
    parser.add_argument(
        "--property-tax-rate", type=float, default=defaults.property_tax_rate
    )
    parser.add_argument(
        "--maintenance-rate", type=float, default=defaults.maintenance_rate
    )
    parser.add_argument(
        "--annual-insurance", type=float, default=defaults.annual_insurance
    )
    parser.add_argument(
        "--management-fee-rate", type=float, default=defaults.management_fee_rate
    )
    parser.add_argument(
        "--interest-rate", type=float, default=defaults.annual_interest_rate
    )
    parser.add_argument("--max-ltv", type=float, default=0.8)
    parser.add_argument("--grid-step", type=float, default=0.1)
    parser.add_argument(
        "--require-nonnegative-cash-flow",
        action="store_true",
        help="constrain the optimum to cash-flow-neutral or better leverage",
    )
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the rental-property analysis CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        assumptions = PropertyAssumptions(
            property_value=args.property_value,
            monthly_rent=args.monthly_rent,
            annual_appreciation_rate=args.appreciation_rate,
            vacancy_rate=args.vacancy_rate,
            property_tax_rate=args.property_tax_rate,
            maintenance_rate=args.maintenance_rate,
            annual_insurance=args.annual_insurance,
            management_fee_rate=args.management_fee_rate,
            annual_interest_rate=args.interest_rate,
        )
        scenarios = analyze_ltvs(assumptions, ltv_grid(args.max_ltv, args.grid_step))
        optimum = optimize_ltv(
            assumptions,
            max_ltv=args.max_ltv,
            require_nonnegative_cash_flow=args.require_nonnegative_cash_flow,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.format == "json":
        print(
            json.dumps(
                {
                    "assumptions": asdict(assumptions),
                    "scenarios": [_metrics_dict(item) for item in scenarios],
                    "optimum": _metrics_dict(optimum),
                },
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
    else:
        print(_format_table(scenarios))
        constraint = (
            " with non-negative cash flow" if args.require_nonnegative_cash_flow else ""
        )
        print(
            f"\nOptimal LTV{constraint}: {optimum.ltv:.2%} ({optimum.roe_percent:.2f}% ROE)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
