from fastapi import APIRouter

from app.policy.models import ResearchPolicy
from app.policy.service import (
    get_active_policy,
    update_active_policy,
)


router = APIRouter(
    prefix="/policy",
    tags=["Policy"],
)


@router.get(
    "",
    response_model=ResearchPolicy,
)
def read_active_policy():
    return get_active_policy()


@router.put(
    "",
    response_model=ResearchPolicy,
)
def replace_active_policy(
    policy: ResearchPolicy,
):
    return update_active_policy(policy)