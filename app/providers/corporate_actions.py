from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SplitEvent:
    effective_date: date
    split_factor: Decimal


@dataclass(frozen=True)
class DividendEvent:
    ex_dividend_date: date

    amount: Decimal

    declaration_date: date | None = None
    record_date: date | None = None
    payment_date: date | None = None