from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from api.models import BRANCH_CODE, RULE_ID, ExceptionPage
from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["exceptions"])


@router.get("/exceptions", response_model=ExceptionPage)
def exceptions(
    rule_id: Annotated[str | None, Query(pattern=RULE_ID, examples=["APP-03"])] = None,
    action: Literal["FLAG", "REJECT"] | None = None,
    branch_code: Annotated[str | None, Query(pattern=BRANCH_CODE)] = None,
    batch_id: Annotated[str | None, Query(max_length=50, examples=["batch_001"])] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    repository: GoldRepository = Depends(get_repository),
) -> dict:
    """Data-quality exception records, paged and ordered by rule_id, record_key."""
    return repository.get_exceptions(
        rule_id=rule_id, action=action, branch_code=branch_code, batch_id=batch_id, limit=limit, offset=offset
    )
