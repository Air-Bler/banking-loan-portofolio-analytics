from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from api.models import APPLICATION_ID, ConnectedExposure
from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["graph"])


@router.get("/graph/applications/{application_id}/connected-exposure", response_model=ConnectedExposure)
def connected_exposure(
    application_id: Annotated[str, Path(pattern=APPLICATION_ID, examples=["LA000225"])],
    repository: GoldRepository = Depends(get_repository),
) -> dict:
    """The applications of every member of the applicant's household."""
    result = repository.connected_exposure(application_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return result
