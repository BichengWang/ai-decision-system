"""Practice-area income simulation for solo lawyers.

Run:
  python /Users/bichengwang/codes/py-notebook/src/lawyer_income_simulation.py --samples 10000

No third-party dependencies required.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
from dataclasses import dataclass
from typing import Dict, Iterable, List, Literal, Sequence, Tuple


BillingModel = Literal["hourly", "flat", "contingency"]


@dataclass(frozen=True)
class DomainConfig:
    """Configuration for a practice domain.

    All monetary values are in USD. Means/stds are for Normal distributions unless
    noted otherwise. Values are clamped where appropriate to avoid negatives.
    """

    name: str
    billing_model: BillingModel
    # Hourly billing
    hourly_rate_mean: float = 0.0
    hourly_rate_std: float = 0.0
    utilization_mean: float = 0.0  # fraction in [0, 1]
    utilization_std: float = 0.0
    hours_capacity_per_year: int = 2000

    # Flat fee
    flat_fee_mean: float = 0.0
    flat_fee_std: float = 0.0
    cases_per_year_mean: float = 0.0
    cases_per_year_std: float = 0.0

    # Contingency
    success_rate_mean: float = 0.0  # fraction in [0, 1]
    success_rate_std: float = 0.0
    contingency_fee_pct_mean: float = 0.0  # fraction in [0, 1]
    contingency_fee_pct_std: float = 0.0
    settlement_mean: float = 0.0  # average settlement per winning case
    settlement_std: float = 0.0
    cases_litigated_per_year_mean: float = 0.0
    cases_litigated_per_year_std: float = 0.0

    # Expenses
    fixed_expense_mean: float = 20000.0
    fixed_expense_std: float = 5000.0
    variable_expense_pct_mean: float = 0.2  # fraction of revenue
    variable_expense_pct_std: float = 0.05


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _sample_normal_positive(mean: float, std: float, minimum: float = 0.0) -> float:
    if std <= 0:
        return max(mean, minimum)
    return max(random.gauss(mean, std), minimum)


def _sample_fraction(mean: float, std: float) -> float:
    if std <= 0:
        return _clamp(mean, 0.0, 1.0)
    return _clamp(random.gauss(mean, std), 0.0, 1.0)


def _binomial_draw(num_trials: int, success_prob: float) -> int:
    # Simple binomial via Bernoulli trials; performant enough for small counts
    wins = 0
    for _ in range(num_trials):
        if random.random() < success_prob:
            wins += 1
    return wins


def simulate_one_year(config: DomainConfig) -> float:
    """Simulate net income for a single year given a domain config."""

    revenue = 0.0

    if config.billing_model == "hourly":
        utilization = _sample_fraction(config.utilization_mean, config.utilization_std)
        hours_worked = int(round(config.hours_capacity_per_year * utilization))
        hourly_rate = _sample_normal_positive(config.hourly_rate_mean, config.hourly_rate_std)
        revenue = float(hours_worked) * hourly_rate

    elif config.billing_model == "flat":
        cases = int(round(_sample_normal_positive(config.cases_per_year_mean, config.cases_per_year_std)))
        flat_fee = _sample_normal_positive(config.flat_fee_mean, config.flat_fee_std)
        revenue = float(cases) * flat_fee

    elif config.billing_model == "contingency":
        cases = int(
            round(
                _sample_normal_positive(
                    config.cases_litigated_per_year_mean, config.cases_litigated_per_year_std
                )
            )
        )
        success_rate = _sample_fraction(config.success_rate_mean, config.success_rate_std)
        wins = _binomial_draw(cases, success_rate)
        fee_pct = _sample_fraction(config.contingency_fee_pct_mean, config.contingency_fee_pct_std)
        avg_settlement = _sample_normal_positive(config.settlement_mean, config.settlement_std)
        revenue = float(wins) * fee_pct * avg_settlement

    else:
        raise ValueError(f"Unsupported billing model: {config.billing_model}")

    fixed_expense = _sample_normal_positive(config.fixed_expense_mean, config.fixed_expense_std)
    variable_pct = _sample_fraction(config.variable_expense_pct_mean, config.variable_expense_pct_std)
    expenses = fixed_expense + variable_pct * revenue
    net_income = revenue - expenses
    return max(net_income, -1_000_000.0)  # clamp extremely negative tails


def simulate_many(config: DomainConfig, num_samples: int, seed: int | None = None) -> List[float]:
    if seed is not None:
        random.seed(seed)
    return [simulate_one_year(config) for _ in range(num_samples)]


def summarize(samples: Sequence[float]) -> Dict[str, float]:
    if not samples:
        return {"mean": 0.0, "p10": 0.0, "p50": 0.0, "p90": 0.0}
    sorted_vals = sorted(samples)
    n = len(sorted_vals)

    def pct(p: float) -> float:
        if n == 1:
            return sorted_vals[0]
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[f] * (c - k)
        d1 = sorted_vals[c] * (k - f)
        return d0 + d1

    return {
        "mean": statistics.fmean(sorted_vals),
        "p10": pct(0.10),
        "p50": pct(0.50),
        "p90": pct(0.90),
    }


def default_domain_configs() -> List[DomainConfig]:
    return [
        DomainConfig(
            name="Corporate",
            billing_model="hourly",
            hourly_rate_mean=300.0,
            hourly_rate_std=50.0,
            utilization_mean=0.7,
            utilization_std=0.08,
            fixed_expense_mean=35000.0,
            fixed_expense_std=8000.0,
            variable_expense_pct_mean=0.22,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Criminal Defense",
            billing_model="flat",
            flat_fee_mean=5000.0,
            flat_fee_std=1000.0,
            cases_per_year_mean=40.0,
            cases_per_year_std=8.0,
            fixed_expense_mean=25000.0,
            fixed_expense_std=6000.0,
            variable_expense_pct_mean=0.18,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Family Law",
            billing_model="hourly",
            hourly_rate_mean=250.0,
            hourly_rate_std=40.0,
            utilization_mean=0.68,
            utilization_std=0.08,
            fixed_expense_mean=22000.0,
            fixed_expense_std=5000.0,
            variable_expense_pct_mean=0.2,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Personal Injury",
            billing_model="contingency",
            success_rate_mean=0.25,
            success_rate_std=0.06,
            contingency_fee_pct_mean=0.33,
            contingency_fee_pct_std=0.03,
            settlement_mean=80_000.0,
            settlement_std=25_000.0,
            cases_litigated_per_year_mean=18.0,
            cases_litigated_per_year_std=5.0,
            fixed_expense_mean=40000.0,
            fixed_expense_std=12000.0,
            variable_expense_pct_mean=0.28,
            variable_expense_pct_std=0.07,
        ),
        DomainConfig(
            name="Immigration",
            billing_model="flat",
            flat_fee_mean=3000.0,
            flat_fee_std=600.0,
            cases_per_year_mean=55.0,
            cases_per_year_std=10.0,
            fixed_expense_mean=20000.0,
            fixed_expense_std=5000.0,
            variable_expense_pct_mean=0.15,
            variable_expense_pct_std=0.04,
        ),
        DomainConfig(
            name="Intellectual Property",
            billing_model="hourly",
            hourly_rate_mean=380.0,
            hourly_rate_std=60.0,
            utilization_mean=0.66,
            utilization_std=0.07,
            fixed_expense_mean=38000.0,
            fixed_expense_std=9000.0,
            variable_expense_pct_mean=0.22,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Real Estate",
            billing_model="flat",
            flat_fee_mean=1500.0,
            flat_fee_std=300.0,
            cases_per_year_mean=90.0,
            cases_per_year_std=20.0,
            fixed_expense_mean=18000.0,
            fixed_expense_std=4000.0,
            variable_expense_pct_mean=0.12,
            variable_expense_pct_std=0.03,
        ),
        DomainConfig(
            name="Tax",
            billing_model="hourly",
            hourly_rate_mean=320.0,
            hourly_rate_std=50.0,
            utilization_mean=0.64,
            utilization_std=0.07,
            fixed_expense_mean=26000.0,
            fixed_expense_std=6000.0,
            variable_expense_pct_mean=0.18,
            variable_expense_pct_std=0.04,
        ),
    ]


def format_currency(value: float) -> str:
    sign = "-" if value < 0 else ""
    abs_val = abs(value)
    return f"{sign}${abs_val:,.0f}"


def print_summary_table(domain_to_stats: Dict[str, Dict[str, float]]) -> None:
    name_col = "Domain"
    headers = [name_col, "Mean", "P10", "Median", "P90"]
    col_widths = [max(len(name_col), max((len(n) for n in domain_to_stats), default=0))]
    col_widths += [10, 10, 10, 10]

    def hline() -> str:
        return "+" + "+".join("-" * w for w in col_widths) + "+"

    def row(cols: Sequence[str]) -> str:
        return "|" + "|".join(c.ljust(w) for c, w in zip(cols, col_widths)) + "|"

    print(hline())
    print(row(headers))
    print(hline())
    for name, stats in domain_to_stats.items():
        cols = [
            name,
            format_currency(stats["mean"]),
            format_currency(stats["p10"]),
            format_currency(stats["p50"]),
            format_currency(stats["p90"]),
        ]
        print(row(cols))
    print(hline())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate lawyer income across domains")
    parser.add_argument("--samples", type=int, default=5000, help="Monte Carlo samples per domain")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    configs = default_domain_configs()
    results: Dict[str, Dict[str, float]] = {}
    for cfg in configs:
        samples = simulate_many(cfg, num_samples=args.samples, seed=args.seed)
        results[cfg.name] = summarize(samples)
    print_summary_table(results)


if __name__ == "__main__":
    main()


