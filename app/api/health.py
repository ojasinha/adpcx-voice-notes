from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.common import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(settings: SettingsDep) -> HealthOut:
    return HealthOut(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )
