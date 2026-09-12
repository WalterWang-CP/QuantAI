from dataclasses import dataclass
from datetime import date

from app.db.models.identity import Listing
from app.providers.base import MarketBar


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    rule_code: str
    message: str

    trading_date: date | None = None


def validate_daily_price_bars(
    bars: list[MarketBar],
    listing: Listing,
) -> list[ValidationIssue]:
    issues = []

    if not bars:
        issues.append(
            ValidationIssue(
                severity="error",
                rule_code="NO_DATA",
                message=(
                    "Provider returned no "
                    "daily price bars."
                ),
            )
        )

        return issues

    seen_dates = set()

    for bar in bars:
        if bar.trading_date in seen_dates:
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="DUPLICATE_DATE",
                    message=(
                        "Duplicate trading date "
                        "returned by provider."
                    ),
                    trading_date=bar.trading_date,
                )
            )

        seen_dates.add(
            bar.trading_date
        )

        if (
            bar.open_price <= 0
            or bar.high_price <= 0
            or bar.low_price <= 0
            or bar.close_price <= 0
        ):
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="NON_POSITIVE_PRICE",
                    message=(
                        "One or more OHLC prices "
                        "are zero or negative."
                    ),
                    trading_date=bar.trading_date,
                )
            )

        if bar.high_price < bar.low_price:
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="HIGH_BELOW_LOW",
                    message=(
                        "High price is below "
                        "low price."
                    ),
                    trading_date=bar.trading_date,
                )
            )

        if (
            bar.high_price < bar.open_price
            or bar.high_price < bar.close_price
        ):
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="INVALID_HIGH",
                    message=(
                        "High price is below "
                        "open or close."
                    ),
                    trading_date=bar.trading_date,
                )
            )

        if (
            bar.low_price > bar.open_price
            or bar.low_price > bar.close_price
        ):
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="INVALID_LOW",
                    message=(
                        "Low price is above "
                        "open or close."
                    ),
                    trading_date=bar.trading_date,
                )
            )

        if bar.volume < 0:
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="NEGATIVE_VOLUME",
                    message=(
                        "Trading volume "
                        "cannot be negative."
                    ),
                    trading_date=bar.trading_date,
                )
            )

        if (
            listing.start_date is not None
            and bar.trading_date
            < listing.start_date
        ):
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="BEFORE_LISTING_START",
                    message=(
                        "Price data predates "
                        "this listing."
                    ),
                    trading_date=bar.trading_date,
                )
            )

        if (
            listing.end_date is not None
            and bar.trading_date
            > listing.end_date
        ):
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule_code="AFTER_LISTING_END",
                    message=(
                        "Price data occurs after "
                        "this listing ended."
                    ),
                    trading_date=bar.trading_date,
                )
            )

    return issues