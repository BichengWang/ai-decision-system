from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from src.fin.broker_interact.robinhood_analysis import (
    format_summary,
    load_report,
    main,
    money_to_float,
    summarize_transactions,
)


class MoneyParsingTests(unittest.TestCase):
    def test_supported_currency_formats(self) -> None:
        examples = {
            "$1,234.50": 1234.5,
            "($1,234.50)": -1234.5,
            "-$2.25": -2.25,
            "$-2.25": -2.25,
            " +$2.25 ": 2.25,
            "": 0.0,
            "--": 0.0,
            None: 0.0,
        }
        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                self.assertEqual(money_to_float(raw), expected)

    def test_malformed_or_nonfinite_values_fail(self) -> None:
        for raw in ("($1", "$1$", "abc", "(-$1)", float("inf"), True):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                money_to_float(raw)


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.report_path = Path(self.temp_dir.name) / "report.csv"
        self.report_path.write_text(
            "Instrument,Trans Code,Amount,Price\n"
            'TSLA,Buy,"$1,000.00","$200.00"\n'
            "tsla,Sell,($250.00),$250.00\n"
            "AAPL,Buy,$500.00,$100.00\n"
            "TSLA,Dividend,$4.00,$0.00\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_and_case_insensitive_summary(self) -> None:
        report = load_report(self.report_path)
        original = report.copy(deep=True)

        summary = summarize_transactions(report, instrument="tsla")

        expected = pd.DataFrame(
            {
                "Trans Code": ["Buy", "Sell"],
                "Instrument": ["TSLA", "tsla"],
                "transaction_count": [1, 1],
                "total_amount": [1000.0, -250.0],
            }
        )
        assert_frame_equal(summary.reset_index(drop=True), expected)
        assert_frame_equal(report, original)

    def test_missing_columns_are_reported(self) -> None:
        bad_path = Path(self.temp_dir.name) / "bad.csv"
        bad_path.write_text("Instrument,Amount\nTSLA,$1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Trans Code"):
            load_report(bad_path)
        with self.assertRaisesRegex(ValueError, "Trans Code"):
            summarize_transactions(pd.DataFrame({"Instrument": [], "Amount": []}))

    def test_bad_money_identifies_the_column(self) -> None:
        self.report_path.write_text(
            "Instrument,Trans Code,Amount,Price\nTSLA,Buy,not-money,$1\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "money column 'Amount'"):
            load_report(self.report_path)

    def test_empty_summary_has_clear_table_output(self) -> None:
        report = load_report(self.report_path)
        summary = summarize_transactions(report, instrument="NVDA")
        self.assertEqual(format_summary(summary), "No matching transactions.")
        self.assertEqual(format_summary(summary, "json"), "[]")

    def test_cli_can_emit_csv(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [str(self.report_path), "--instrument", "TSLA", "--format", "csv"]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "Trans Code,Instrument,transaction_count,total_amount", output.getvalue()
        )
        self.assertIn("Buy,TSLA,1,1000.0", output.getvalue())


if __name__ == "__main__":
    unittest.main()
