from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal


class MarketBar:
    def __init__(
        self,
        trading_date: date,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        volume: int,
    ):
        self.trading_date = trading_date
        self.open_price = open_price
        self.high_price = high_price
        self.low_price = low_price
        self.close_price = close_price
        self.volume = volume


class MarketDataProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def get_daily_prices(
        self,
        symbol: str,
        full_history: bool = False,
    ) -> list[MarketBar]:
        pass