from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class MarketBar:
    trading_date: date

    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal

    volume: int


@dataclass(frozen=True)
class RawProviderResponse:
    body: bytes
    content_type: str | None


class MarketDataProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def fetch_daily_response(
        self,
        symbol: str,
        full_history: bool = False,
    ) -> RawProviderResponse:
        pass

    @abstractmethod
    def parse_daily_prices(
        self,
        response: RawProviderResponse,
    ) -> list[MarketBar]:
        pass

    def get_daily_prices(
        self,
        symbol: str,
        full_history: bool = False,
    ) -> list[MarketBar]:
        raw_response = self.fetch_daily_response(
            symbol=symbol,
            full_history=full_history,
        )

        return self.parse_daily_prices(
            raw_response
        )