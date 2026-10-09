from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["branches"])


@router.get("/branches/{branch_code}/summary")
def branch_summary(
    branch_code: str,
    repository: GoldRepository = Depends(get_repository),
) -> dict[str, Any]:
    result = repository.branch_summary(branch_code)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Branch {branch_code} not found")
    return result
