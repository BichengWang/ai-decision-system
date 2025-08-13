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
import base64
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Literal, Sequence


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
        return {"mean": 0.0, "p10": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0}
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
        "p99": pct(0.99),
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
            name="Employment",
            billing_model="hourly",
            hourly_rate_mean=280.0,
            hourly_rate_std=45.0,
            utilization_mean=0.65,
            utilization_std=0.07,
            fixed_expense_mean=24000.0,
            fixed_expense_std=6000.0,
            variable_expense_pct_mean=0.18,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Bankruptcy",
            billing_model="flat",
            flat_fee_mean=2500.0,
            flat_fee_std=500.0,
            cases_per_year_mean=60.0,
            cases_per_year_std=12.0,
            fixed_expense_mean=22000.0,
            fixed_expense_std=5000.0,
            variable_expense_pct_mean=0.15,
            variable_expense_pct_std=0.04,
        ),
        DomainConfig(
            name="Estate Planning",
            billing_model="flat",
            flat_fee_mean=3000.0,
            flat_fee_std=700.0,
            cases_per_year_mean=50.0,
            cases_per_year_std=10.0,
            fixed_expense_mean=20000.0,
            fixed_expense_std=5000.0,
            variable_expense_pct_mean=0.12,
            variable_expense_pct_std=0.03,
        ),
        DomainConfig(
            name="Civil Litigation",
            billing_model="hourly",
            hourly_rate_mean=310.0,
            hourly_rate_std=55.0,
            utilization_mean=0.62,
            utilization_std=0.07,
            fixed_expense_mean=40000.0,
            fixed_expense_std=10000.0,
            variable_expense_pct_mean=0.22,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Elder Law",
            billing_model="hourly",
            hourly_rate_mean=240.0,
            hourly_rate_std=40.0,
            utilization_mean=0.60,
            utilization_std=0.07,
            fixed_expense_mean=18000.0,
            fixed_expense_std=4000.0,
            variable_expense_pct_mean=0.15,
            variable_expense_pct_std=0.04,
        ),
        DomainConfig(
            name="Environmental",
            billing_model="hourly",
            hourly_rate_mean=360.0,
            hourly_rate_std=60.0,
            utilization_mean=0.58,
            utilization_std=0.06,
            fixed_expense_mean=42000.0,
            fixed_expense_std=12000.0,
            variable_expense_pct_mean=0.24,
            variable_expense_pct_std=0.06,
        ),
        DomainConfig(
            name="Securities",
            billing_model="hourly",
            hourly_rate_mean=420.0,
            hourly_rate_std=70.0,
            utilization_mean=0.55,
            utilization_std=0.06,
            fixed_expense_mean=45000.0,
            fixed_expense_std=13000.0,
            variable_expense_pct_mean=0.25,
            variable_expense_pct_std=0.06,
        ),
        DomainConfig(
            name="Construction",
            billing_model="hourly",
            hourly_rate_mean=300.0,
            hourly_rate_std=45.0,
            utilization_mean=0.62,
            utilization_std=0.07,
            fixed_expense_mean=30000.0,
            fixed_expense_std=8000.0,
            variable_expense_pct_mean=0.20,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Entertainment",
            billing_model="hourly",
            hourly_rate_mean=350.0,
            hourly_rate_std=60.0,
            utilization_mean=0.60,
            utilization_std=0.07,
            fixed_expense_mean=38000.0,
            fixed_expense_std=9000.0,
            variable_expense_pct_mean=0.22,
            variable_expense_pct_std=0.05,
        ),
        DomainConfig(
            name="Healthcare",
            billing_model="hourly",
            hourly_rate_mean=340.0,
            hourly_rate_std=55.0,
            utilization_mean=0.60,
            utilization_std=0.07,
            fixed_expense_mean=36000.0,
            fixed_expense_std=9000.0,
            variable_expense_pct_mean=0.21,
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
    print(render_summary_table(domain_to_stats))


def render_summary_table(domain_to_stats: Dict[str, Dict[str, float]]) -> str:
    name_col = "Domain"
    headers = [name_col, "Mean", "P10", "Median", "P90", "P99"]
    col_widths = [max(len(name_col), max((len(n) for n in domain_to_stats), default=0))]
    col_widths += [10, 10, 10, 10, 10]

    def hline() -> str:
        return "+" + "+".join("-" * w for w in col_widths) + "+"

    def row(cols: Sequence[str]) -> str:
        return "|" + "|".join(c.ljust(w) for c, w in zip(cols, col_widths)) + "|"

    lines: List[str] = []
    lines.append(hline())
    lines.append(row(headers))
    lines.append(hline())
    for name, stats in domain_to_stats.items():
        cols = [
            name,
            format_currency(stats["mean"]),
            format_currency(stats["p10"]),
            format_currency(stats["p50"]),
            format_currency(stats["p90"]),
            format_currency(stats["p99"]),
        ]
        lines.append(row(cols))
    lines.append(hline())
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate lawyer income across domains")
    parser.add_argument("--samples", type=int, default=5000, help="Monte Carlo samples per domain")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--send-email-to",
        type=str,
        default=None,
        help="Email address to send results to using Gmail API",
    )
    parser.add_argument(
        "--gmail-creds-path",
        type=str,
        default="/Users/bichengwang/codes/diary/.config/credential/gcp/gcp-oauth.keys.json",
        help="Path to Google OAuth client secrets JSON",
    )
    parser.add_argument(
        "--gmail-token-path",
        type=str,
        default="/Users/bichengwang/codes/diary/.config/credential/gcp/token.json",
        help="Path to store OAuth token JSON (created on first run)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    configs = default_domain_configs()
    results: Dict[str, Dict[str, float]] = {}
    for cfg in configs:
        samples = simulate_many(cfg, num_samples=args.samples, seed=args.seed)
        results[cfg.name] = summarize(samples)
    table_text = render_summary_table(results)
    print(table_text)

    if args.send_email_to:
        subject = (
            f"Lawyer income simulation results (samples={args.samples}, seed={args.seed}) "
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
        )
        body = (
            "Here are the simulation results.\n\n" + table_text + "\n\n"
            "Generated by lawyer_income_simulation.py"
        )
        try:
            service = _build_gmail_service(
                credentials_path=args.gmail_creds_path, token_path=args.gmail_token_path
            )
            _send_email_via_gmail(service=service, to_address=args.send_email_to, subject=subject, body=body)
            print(f"Email sent to {args.send_email_to}")
        except Exception as exc:  # noqa: BLE001
            print(
                "Failed to send email via Gmail API. "
                "Make sure required packages are installed and credentials are valid."
            )
            print(str(exc))


def _build_gmail_service(*, credentials_path: str, token_path: str):
    """Create an authenticated Gmail API service with OAuth user consent on first run."""
    scopes = ["https://www.googleapis.com/auth/gmail.send"]
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
    except Exception as e:  # type: ignore
        raise RuntimeError(
            "Missing Gmail dependencies. Install: "
            "pip install --upgrade google-auth google-auth-oauthlib google-api-python-client"
        ) from e

    creds = None
    token_file = Path(token_path)
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    return service


def _send_email_via_gmail(*, service, to_address: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


if __name__ == "__main__":
    main()
