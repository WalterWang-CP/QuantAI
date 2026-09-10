from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class MarketBarRead(BaseModel):
    trading_date: date

    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal

    volume: int


class MarketDataPreview(BaseModel):
    provider: str
    symbol: str

    full_history_requested: bool

    bar_count: int

    first_date: date | None
    last_date: date | None

    sample: list[MarketBarRead]