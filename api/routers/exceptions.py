from typing import Any

from fastapi import APIRouter, Depends, Query

from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["exceptions"])


@router.get("/exceptions")
def exceptions(
    rule_id: str | None = None,
    action: str | None = None,
    branch_code: str | None = None,
    batch_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repository: GoldRepository = Depends(get_repository),
) -> dict[str, Any]:
    return repository.get_exceptions(
        rule_id=rule_id,
        action=action,
        branch_code=branch_code,
        batch_id=batch_id,
        limit=limit,
        offset=offset,
    )
