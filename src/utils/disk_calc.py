"""Convert storage sizes between decimal and binary units.

This module replaces the former ``disk_calc.ipynb`` scratch calculation with a
small importable API and command-line interface.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from typing import Sequence

Number = int | float | str | Decimal

_UNIT_FACTORS: dict[str, Decimal] = {
    "B": Decimal(1),
    "KB": Decimal(1_000),
    "MB": Decimal(1_000) ** 2,
    "GB": Decimal(1_000) ** 3,
    "TB": Decimal(1_000) ** 4,
    "PB": Decimal(1_000) ** 5,
    "KiB": Decimal(1_024),
    "MiB": Decimal(1_024) ** 2,
    "GiB": Decimal(1_024) ** 3,
    "TiB": Decimal(1_024) ** 4,
    "PiB": Decimal(1_024) ** 5,
}

_UNIT_ALIASES = {
    "BYTE": "B",
    "BYTES": "B",
    **{unit.upper(): unit for unit in _UNIT_FACTORS},
}


def _canonical_unit(unit: str) -> str:
    """Return the canonical spelling for a supported storage unit."""
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError("unit must be a non-empty string")
    try:
        return _UNIT_ALIASES[unit.strip().upper()]
    except KeyError as exc:
        supported = ", ".join(_UNIT_FACTORS)
        raise ValueError(
            f"unsupported unit {unit!r}; choose one of: {supported}"
        ) from exc


def _decimal(value: Number) -> Decimal:
    """Convert a number without introducing binary floating-point artifacts."""
    if isinstance(value, bool):
        raise ValueError("size must be a number, not a boolean")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid size: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("size must be finite")
    if result < 0:
        raise ValueError("size must be non-negative")
    return result


def convert_size(value: Number, from_unit: str = "B", to_unit: str = "TiB") -> Decimal:
    """Convert *value* from one storage unit to another.

    Decimal units (KB, MB, GB, ...) use powers of 1000. Binary units (KiB,
    MiB, GiB, ...) use powers of 1024. A :class:`~decimal.Decimal` is returned
    so large capacities retain their precision.
    """
    source = _canonical_unit(from_unit)
    target = _canonical_unit(to_unit)
    return _decimal(value) * _UNIT_FACTORS[source] / _UNIT_FACTORS[target]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("value", help="non-negative storage size")
    parser.add_argument("--from-unit", default="B", help="input unit (default: B)")
    parser.add_argument("--to-unit", default="TiB", help="output unit (default: TiB)")
    parser.add_argument(
        "--precision",
        type=int,
        default=4,
        help="digits after the decimal point (default: 4)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the storage conversion CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.precision < 0:
        parser.error("--precision must be non-negative")

    try:
        result = convert_size(args.value, args.from_unit, args.to_unit)
        target = _canonical_unit(args.to_unit)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"{result:.{args.precision}f} {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
