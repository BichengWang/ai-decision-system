"""Load and summarize Robinhood account-history CSV exports.

Unlike the notebook this module has no machine-specific paths or import-time
I/O. It can be imported as a library or run directly as a command-line tool.
"""

from __future__ import annotations

import argparse
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
from tabulate import tabulate

REQUIRED_COLUMNS = frozenset({"Instrument", "Trans Code", "Amount"})
DEFAULT_MONEY_COLUMNS = ("Amount", "Price")
_EMPTY_MONEY_VALUES = frozenset({"", "-", "--", "N/A", "NA", "NULL", "NONE"})


def money_to_float(value: object) -> float:
    """Parse a currency value from a Robinhood CSV export.

    Dollar signs, thousands separators, surrounding whitespace, and accounting
    negatives such as ``($1,234.50)`` are accepted. Empty export fields map to
    zero, matching the old notebook's behavior. Malformed and non-finite values
    fail loudly rather than contaminating an aggregate.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid currency amounts")
    if isinstance(value, (int, float, Decimal)):
        result = float(value)
        if not math.isfinite(result):
            if isinstance(value, float) and math.isnan(value):
                return 0.0
            raise ValueError(f"currency amount must be finite: {value!r}")
        return result

    text = str(value).strip()
    if text.upper() in _EMPTY_MONEY_VALUES:
        return 0.0

    parenthesized = text.startswith("(") and text.endswith(")")
    if text.startswith("(") != text.endswith(")"):
        raise ValueError(f"malformed accounting amount: {value!r}")
    if parenthesized:
        text = text[1:-1].strip()
        if text.startswith(("+", "-")):
            raise ValueError(f"accounting amount has two signs: {value!r}")

    # Robinhood commonly exports "$1,234.56". Also accept a sign on either
    # side of the dollar symbol ("-$1" and "$-1").
    text = re.sub(r"\s+", "", text).replace(",", "")
    if text.startswith("-$"):
        text = "-" + text[2:]
    elif text.startswith("+$"):
        text = "+" + text[2:]
    elif text.startswith("$"):
        text = text[1:]
    if "$" in text:
        raise ValueError(f"malformed currency amount: {value!r}")

    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"malformed currency amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"currency amount must be finite: {value!r}")
    if parenthesized:
        amount = -amount
    return float(amount)


def load_report(
    file_name: str | Path,
    *,
    money_columns: Iterable[str] = DEFAULT_MONEY_COLUMNS,
    required_columns: Iterable[str] = REQUIRED_COLUMNS,
) -> pd.DataFrame:
    """Load a Robinhood CSV and validate the columns needed for analysis."""
    path = Path(file_name).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Robinhood report does not exist: {path}")

    frame = pd.read_csv(path)
    required = set(required_columns)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"report is missing required columns: {', '.join(missing)}")

    for column in money_columns:
        if column in frame.columns:
            try:
                frame[column] = frame[column].map(money_to_float)
            except ValueError as exc:
                raise ValueError(
                    f"could not parse money column {column!r}: {exc}"
                ) from exc
    return frame


# Backward-compatible name from the notebook, now with an explicit path.
loader = load_report


def summarize_transactions(
    frame: pd.DataFrame,
    *,
    instrument: str | None = None,
    transaction_codes: Iterable[str] = ("Buy", "Sell"),
) -> pd.DataFrame:
    """Aggregate transaction counts and amounts by code and instrument.

    Instrument and transaction-code filters are case-insensitive. The input
    frame is never mutated.
    """
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"data is missing required columns: {', '.join(missing)}")

    codes = tuple(str(code).strip() for code in transaction_codes)
    if not codes or any(not code for code in codes):
        raise ValueError("transaction_codes must contain at least one non-empty code")

    selected = frame.loc[:, ["Trans Code", "Instrument", "Amount"]].copy()
    selected["Amount"] = selected["Amount"].map(money_to_float)
    code_keys = {code.casefold() for code in codes}
    mask = (
        selected["Trans Code"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .isin(code_keys)
    )
    if instrument is not None:
        instrument_key = instrument.strip().casefold()
        if not instrument_key:
            raise ValueError("instrument must not be blank")
        mask &= (
            selected["Instrument"]
            .astype("string")
            .str.strip()
            .str.casefold()
            .eq(instrument_key)
        )

    result = (
        selected.loc[mask]
        .groupby(["Trans Code", "Instrument"], as_index=False, sort=True, dropna=False)
        .agg(transaction_count=("Amount", "size"), total_amount=("Amount", "sum"))
    )
    return result


def format_summary(summary: pd.DataFrame, output_format: str = "table") -> str:
    """Serialize a transaction summary for terminal or file output."""
    if output_format == "table":
        if summary.empty:
            return "No matching transactions."
        return tabulate(
            summary,
            headers="keys",
            tablefmt="grid",
            showindex=False,
            floatfmt=",.2f",
        )
    if output_format == "csv":
        return summary.to_csv(index=False).rstrip("\n")
    if output_format == "json":
        return "[]" if summary.empty else summary.to_json(orient="records", indent=2)
    raise ValueError("output_format must be one of: table, csv, json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Robinhood account-history CSV")
    parser.add_argument("--instrument", help="filter by ticker/instrument")
    parser.add_argument(
        "--code",
        action="append",
        dest="codes",
        help="transaction code to include; repeat as needed (default: Buy and Sell)",
    )
    parser.add_argument("--format", choices=("table", "csv", "json"), default="table")
    parser.add_argument(
        "--output", type=Path, help="write output instead of printing it"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Robinhood report CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        report = load_report(args.report)
        summary = summarize_transactions(
            report,
            instrument=args.instrument,
            transaction_codes=args.codes or ("Buy", "Sell"),
        )
        rendered = format_summary(summary, args.format)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    if args.output:
        args.output.expanduser().write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
