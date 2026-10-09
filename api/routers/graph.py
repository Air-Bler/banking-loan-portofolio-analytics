from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["graph"])


@router.get("/graph/applications/{application_id}/connected-exposure")
def connected_exposure(
    application_id: str,
    repository: GoldRepository = Depends(get_repository),
) -> dict[str, Any]:
    result = repository.connected_exposure(application_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Application {application_id} not found",
        )
    return result
