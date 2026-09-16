import json
from datetime import date
from decimal import Decimal

import httpx

from app.core.config import settings
from app.providers.base import (
    MarketBar,
    MarketDataProvider,
    RawProviderResponse,
)
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTemporaryError,
)


class AlphaVantageProvider(MarketDataProvider):
    BASE_URL = "https://www.alphavantage.co/query"

    @property
    def provider_name(self) -> str:
        return "alpha_vantage"

    def fetch_daily_response(
        self,
        symbol: str,
        full_history: bool = False,
    ) -> RawProviderResponse:
        if settings.alpha_vantage_api_key is None:
            raise ProviderRequestError(
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

        try:
            response = httpx.get(
                self.BASE_URL,
                params=parameters,
                timeout=30.0,
            )

            response.raise_for_status()

        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code

            if status_code == 429:
                raise ProviderRateLimitError(
                    "Alpha Vantage returned HTTP 429."
                ) from error

            if status_code >= 500:
                raise ProviderTemporaryError(
                    f"Alpha Vantage returned "
                    f"HTTP {status_code}."
                ) from error

            raise ProviderRequestError(
                f"Alpha Vantage returned "
                f"HTTP {status_code}."
            ) from error

        except httpx.RequestError as error:
            raise ProviderTemporaryError(
                "Unable to communicate with "
                "Alpha Vantage."
            ) from error

        return RawProviderResponse(
            body=response.content,
            content_type=response.headers.get(
                "content-type"
            ),
        )

    def parse_daily_prices(
        self,
        response: RawProviderResponse,
    ) -> list[MarketBar]:
        try:
            payload = json.loads(
                response.body.decode("utf-8")
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise ProviderTemporaryError(
                "Alpha Vantage returned an "
                "invalid JSON response."
            ) from error

        if "Error Message" in payload:
            raise ProviderRequestError(
                payload["Error Message"]
            )

        information = payload.get(
            "Information"
        )

        note = payload.get(
            "Note"
        )

        provider_message = (
            information
            or note
        )

        if provider_message is not None:
            normalized_message = (
                provider_message.lower()
            )

            rate_limit_terms = (
                "rate limit",
                "api call frequency",
                "call frequency",
                "requests per day",
                "standard api usage limit",
            )

            if any(
                term in normalized_message
                for term in rate_limit_terms
            ):
                raise ProviderRateLimitError(
                    provider_message
                )

            if information is not None:
                raise ProviderRequestError(
                    provider_message
                )

            raise ProviderTemporaryError(
                provider_message
            )

        time_series = payload.get(
            "Time Series (Daily)"
        )

        if time_series is None:
            raise ProviderTemporaryError(
                "Alpha Vantage returned no "
                "daily time-series data."
            )

        bars = []

        try:
            for date_text, values in time_series.items():
                bars.append(
                    MarketBar(
                        trading_date=
                            date.fromisoformat(
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
                )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ProviderTemporaryError(
                "Alpha Vantage returned an "
                "unexpected daily-data structure."
            ) from error

        bars.sort(
            key=lambda bar: bar.trading_date
        )

        return bars