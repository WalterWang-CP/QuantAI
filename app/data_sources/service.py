from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.market_data import (
    DataSource,
)


def get_or_create_data_source(
    database: Session,
    provider_name: str,
    dataset_name: str,
) -> DataSource:
    statement = select(
        DataSource
    ).where(
        DataSource.provider_name
        == provider_name,

        DataSource.dataset_name
        == dataset_name,
    )

    source = database.scalar(
        statement
    )

    if source is not None:
        return source

    source = DataSource(
        provider_name=provider_name,
        dataset_name=dataset_name,
    )

    database.add(source)
    database.commit()
    database.refresh(source)

    return source