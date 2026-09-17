from datetime import date, timedelta

import pandas_market_calendars as mcal


class UnsupportedExchangeCalendar(
    ValueError
):
    pass


EXCHANGE_CALENDAR_MAP = {
    "NASDAQ": "NYSE",
    "XNAS": "NYSE",

    "NYSE": "NYSE",
    "XNYS": "NYSE",

    "AMEX": "NYSE",
    "NYSEAMERICAN": "NYSE",

    "ARCA": "NYSE",
    "NYSEARCA": "NYSE",
}


def get_calendar_name(
    exchange_code: str,
) -> str:
    normalized_code = (
        exchange_code
        .strip()
        .upper()
    )

    calendar_name = (
        EXCHANGE_CALENDAR_MAP.get(
            normalized_code
        )
    )

    if calendar_name is None:
        raise UnsupportedExchangeCalendar(
            "No market calendar is configured "
            f"for exchange '{exchange_code}'."
        )

    return calendar_name


def get_expected_sessions(
    exchange_code: str,
    start_date: date,
    end_date: date,
) -> list[date]:
    if start_date > end_date:
        return []

    calendar_name = get_calendar_name(
        exchange_code
    )

    calendar = mcal.get_calendar(
        calendar_name
    )

    schedule = calendar.schedule(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )

    return [
        timestamp.date()
        for timestamp in schedule.index
    ]


def get_recent_sessions(
    exchange_code: str,
    end_date: date,
    count: int,
) -> list[date]:
    if count <= 0:
        return []

    lookback_days = max(
        365,
        count * 4,
    )

    sessions = []

    while (
        len(sessions) < count
        and lookback_days <= 5000
    ):
        start_date = (
            end_date
            - timedelta(
                days=lookback_days
            )
        )

        sessions = get_expected_sessions(
            exchange_code=
                exchange_code,
            start_date=start_date,
            end_date=end_date,
        )

        lookback_days *= 2

    return sessions[-count:]