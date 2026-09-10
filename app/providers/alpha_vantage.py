from datetime import date
from decimal import Decimal

import httpx

from app.core.config import settings
from app.providers.base import (
    MarketBar,
    MarketDataProvider,
)


class AlphaVantageProvider(MarketDataProvider):
    BASE_URL = "https://www.alphavantage.co/query"

    @property
    def provider_name(self) -> str:
        return "alpha_vantage"

    def get_daily_prices(
        self,
        symbol: str,
        full_history: bool = False,
    ) -> list[MarketBar]:
        if settings.alpha_vantage_api_key is None:
            raise RuntimeError(
                "Alpha Vantage API key is not configured."
            )

        output_size = (
            "full"
            if full_history
            else "compact"
        )

        parameters = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "outputsize": output_size,
            "apikey": settings.alpha_vantage_api_key,
        }

        response = httpx.get(
            self.BASE_URL,
            params=parameters,
            timeout=30.0,
        )

        response.raise_for_status()

        payload = response.json()

        if "Error Message" in payload:
            raise ValueError(
                payload["Error Message"]
            )

        if "Information" in payload:
            raise RuntimeError(
                payload["Information"]
            )

        if "Note" in payload:
            raise RuntimeError(
                payload["Note"]
            )

        time_series = payload.get(
            "Time Series (Daily)"
        )

        if time_series is None:
            raise RuntimeError(
                "Alpha Vantage returned no daily time-series data."
            )

        bars = []

        for date_text, values in time_series.items():
            bar = MarketBar(
                trading_date=date.fromisoformat(
                    date_text
                ),
                open_price=Decimal(
                    values["1. open"]
                ),
                high_price=Decimal(
                    values["2. high"]
                ),
                low_price=Decimal(
                    values["3. low"]
                ),
                close_price=Decimal(
                    values["4. close"]
                ),
                volume=int(
                    values["5. volume"]
                ),
            )

            bars.append(bar)

        bars.sort(
            key=lambda bar: bar.trading_date
        )

        return bars