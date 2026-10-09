from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from api.models import BRANCH_CODE, BranchSummary
from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["branches"])


@router.get("/branches/{branch_code}/summary", response_model=BranchSummary)
def branch_summary(
    branch_code: Annotated[str, Path(pattern=BRANCH_CODE, examples=["BR003"])],
    repository: GoldRepository = Depends(get_repository),
) -> dict:
    """All KPIs for one branch, plus the same KPIs by product."""
    result = repository.branch_summary(branch_code)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Branch {branch_code} not found")
    return result
