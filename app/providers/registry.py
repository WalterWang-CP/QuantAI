import uuid
from collections.abc import (
    Callable,
    Mapping,
)
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.market_data.service import (
    import_alpha_vantage_daily_prices,
)
from app.providers.errors import (
    ProviderCapabilityError,
)


RetrievalImporter = Callable[
    [
        Session,
        uuid.UUID,
        bool,
        date | None,
        date | None,
    ],
    dict,
]


@dataclass(frozen=True)
class DatasetRegistration:
    dataset_name: str

    importer: RetrievalImporter

    full_history_available: (
        Callable[
            [],
            bool,
        ]
    )


@dataclass(frozen=True)
class ProviderRegistration:
    provider_name: str

    daily_budget: Callable[
        [],
        int | None,
    ]

    datasets: Mapping[
        str,
        DatasetRegistration,
    ]


def alpha_vantage_daily_budget(
) -> int | None:
    return (
        settings
        .alpha_vantage_batch_daily_budget
    )


def alpha_vantage_full_history_available(
) -> bool:
    return (
        settings
        .alpha_vantage_full_history_enabled
    )


ALPHA_VANTAGE_DAILY = (
    DatasetRegistration(
        dataset_name=
            "TIME_SERIES_DAILY",

        importer=
            import_alpha_vantage_daily_prices,

        full_history_available=
            alpha_vantage_full_history_available,
    )
)


ALPHA_VANTAGE = (
    ProviderRegistration(
        provider_name=
            "alpha_vantage",

        daily_budget=
            alpha_vantage_daily_budget,

        datasets={
            ALPHA_VANTAGE_DAILY
            .dataset_name:
                ALPHA_VANTAGE_DAILY,
        },
    )
)


PROVIDER_REGISTRY = {
    ALPHA_VANTAGE.provider_name:
        ALPHA_VANTAGE,
}

def normalize_provider_name(
    provider_name: str,
) -> str:
    return (
        provider_name
        .strip()
        .lower()
    )


def normalize_dataset_name(
    dataset_name: str,
) -> str:
    return (
        dataset_name
        .strip()
        .upper()
    )


def get_provider_registration(
    provider_name: str,
) -> ProviderRegistration:
    normalized_name = (
        normalize_provider_name(
            provider_name
        )
    )

    provider = (
        PROVIDER_REGISTRY.get(
            normalized_name
        )
    )

    if provider is None:
        raise ProviderCapabilityError(
            "Provider is not registered: "
            f"{normalized_name}."
        )

    return provider


def get_dataset_registration(
    provider_name: str,
    dataset_name: str,
) -> DatasetRegistration:
    provider = (
        get_provider_registration(
            provider_name
        )
    )

    normalized_dataset = (
        normalize_dataset_name(
            dataset_name
        )
    )

    dataset = (
        provider.datasets.get(
            normalized_dataset
        )
    )

    if dataset is None:
        raise ProviderCapabilityError(
            f"Provider "
            f"{provider.provider_name} "
            f"does not support dataset "
            f"{normalized_dataset}."
        )

    return dataset


def validate_retrieval_capability(
    provider_name: str,
    dataset_name: str,
    full_history: bool,
) -> None:
    dataset = (
        get_dataset_registration(
            provider_name=
                provider_name,

            dataset_name=
                dataset_name,
        )
    )

    if (
        full_history
        and not dataset
        .full_history_available()
    ):
        raise ProviderCapabilityError(
            f"{provider_name} / "
            f"{dataset_name} does not "
            "have full-history access "
            "enabled."
        )


def get_provider_daily_budget(
    provider_name: str,
) -> int | None:
    provider = (
        get_provider_registration(
            provider_name
        )
    )

    return (
        provider.daily_budget()
    )


def execute_registered_retrieval(
    database: Session,
    provider_name: str,
    dataset_name: str,
    listing_id: uuid.UUID,
    full_history: bool,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    dataset = (
        get_dataset_registration(
            provider_name=
                provider_name,

            dataset_name=
                dataset_name,
        )
    )

    return dataset.importer(
        database=database,
        listing_id=listing_id,
        full_history=full_history,
        start_date=start_date,
        end_date=end_date,
    )

def list_provider_registrations(
) -> list[ProviderRegistration]:
    return list(
        PROVIDER_REGISTRY.values()
    )