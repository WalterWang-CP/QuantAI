import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.universe.schemas import (
    CompanyRankingCreate,
    CompanyRankingRead,
    RankingSnapshotCreate,
    RankingSnapshotRead,
    UniversePreview,
)
from app.universe.service import (
    add_company_ranking,
    build_universe_preview,
    create_ranking_snapshot,
    get_ranking_snapshots,
)
from app.universe.market_cap_ranking import (
    build_market_cap_ranking_snapshot,
)
from app.universe.schemas import (
    MarketCapRankingBuildRequest,
    MarketCapRankingBuildResult,
)
router = APIRouter(
    prefix="/universe",
    tags=["Universe"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/snapshots",
    response_model=RankingSnapshotRead,
    status_code=201,
)
def add_snapshot(
    snapshot_data: RankingSnapshotCreate,
    database: DatabaseSession,
):
    return create_ranking_snapshot(
        database,
        snapshot_data,
    )


@router.get(
    "/snapshots",
    response_model=list[RankingSnapshotRead],
)
def read_snapshots(
    database: DatabaseSession,
):
    return get_ranking_snapshots(database)


@router.post(
    "/snapshots/{snapshot_id}/rankings",
    response_model=CompanyRankingRead,
    status_code=201,
)
def add_ranking(
    snapshot_id: uuid.UUID,
    ranking_data: CompanyRankingCreate,
    database: DatabaseSession,
):
    try:
        return add_company_ranking(
            database,
            snapshot_id,
            ranking_data,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


@router.get(
    "/snapshots/{snapshot_id}/preview",
    response_model=UniversePreview,
)
def preview_universe(
    snapshot_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return build_universe_preview(
            database,
            snapshot_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.post(
"/market-cap-ranking/build",
response_model=
    MarketCapRankingBuildResult,
)
def build_market_cap_ranking(
    payload: MarketCapRankingBuildRequest,
    database: DatabaseSession,
):
    try:
        return (
            build_market_cap_ranking_snapshot(
                database=database,

                ranking_date=
                    payload.ranking_date,

                effective_date=
                    payload.effective_date,

                primary_only=
                    payload.primary_only,

                minimum_candidates=
                    payload.minimum_candidates,
            )
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )