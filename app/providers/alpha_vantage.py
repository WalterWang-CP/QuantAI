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
    ProviderCapabilityError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTemporaryError,
)
from app.providers.corporate_actions import (
    DividendEvent,
    SplitEvent,
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
        if (
            full_history
            and not settings
            .alpha_vantage_full_history_enabled
        ):
            raise ProviderCapabilityError(
                "Alpha Vantage full daily history "
                "is disabled for this QuantAI "
                "configuration. Set "
                "ALPHA_VANTAGE_FULL_HISTORY_ENABLED=true "
                "only when the configured API key "
                "supports outputsize=full."
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

    def _fetch_function_response(
    self,
    function_name: str,
    symbol: str,
    ) -> RawProviderResponse:
        if settings.alpha_vantage_api_key is None:
            raise ProviderRequestError(
                "Alpha Vantage API key is not configured."
            )

        parameters = {
            "function": function_name,
            "symbol": symbol.upper(),
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

    def _decode_payload(
    self,
    response: RawProviderResponse,
    ) -> dict:
        try:
            payload = json.loads(
                response.body.decode("utf-8")
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise ProviderTemporaryError(
                "Alpha Vantage returned invalid JSON."
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

            raise ProviderRequestError(
                provider_message
            )

        return payload

    def fetch_splits_response(
    self,
    symbol: str,
    ) -> RawProviderResponse:
        return self._fetch_function_response(
            function_name="SPLITS",
            symbol=symbol,
        )


    def parse_splits(
        self,
        response: RawProviderResponse,
    ) -> list[SplitEvent]:
        payload = self._decode_payload(
            response
        )

        records = payload.get(
            "data"
        )

        if records is None:
            raise ProviderTemporaryError(
                "Alpha Vantage returned no "
                "split data field."
            )

        events = []

        try:
            for record in records:
                events.append(
                    SplitEvent(
                        effective_date=
                            date.fromisoformat(
                                record[
                                    "effective_date"
                                ]
                            ),

                        split_factor=Decimal(
                            record[
                                "split_factor"
                            ]
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
                "unexpected split-data structure."
            ) from error

        events.sort(
            key=lambda event:
                event.effective_date
        )

        return events


    def fetch_dividends_response(
    self,
    symbol: str,
    ) -> RawProviderResponse:
        return self._fetch_function_response(
            function_name="DIVIDENDS",
            symbol=symbol,
        )


    def parse_optional_date(
        self,
        value: str | None,
    ) -> date | None:
        if value is None:
            return None

        value = value.strip()

        if (
            not value
            or value.lower()
            in {
                "none",
                "null",
            }
        ):
            return None

        return date.fromisoformat(
            value
        )


    def parse_dividends(
        self,
        response: RawProviderResponse,
    ) -> list[DividendEvent]:
        payload = self._decode_payload(
            response
        )

        records = payload.get(
            "data"
        )

        if records is None:
            raise ProviderTemporaryError(
                "Alpha Vantage returned no "
                "dividend data field."
            )

        events = []

        try:
            for record in records:
                events.append(
                    DividendEvent(
                        ex_dividend_date=
                            date.fromisoformat(
                                record[
                                    "ex_dividend_date"
                                ]
                            ),

                        declaration_date=
                            self.parse_optional_date(
                                record.get(
                                    "declaration_date"
                                )
                            ),

                        record_date=
                            self.parse_optional_date(
                                record.get(
                                    "record_date"
                                )
                            ),

                        payment_date=
                            self.parse_optional_date(
                                record.get(
                                    "payment_date"
                                )
                            ),

                        amount=Decimal(
                            record["amount"]
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
                "unexpected dividend-data structure."
            ) from error

        events.sort(
            key=lambda event:
                event.ex_dividend_date
        )

        return events