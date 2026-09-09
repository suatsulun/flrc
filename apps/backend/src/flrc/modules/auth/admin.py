from typing import Annotated

from fastapi import APIRouter, Depends

from flrc.db.models import User
from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(_: Annotated[User, Depends(require_admin)]) -> dict[str, bool]:
    return {"pong": True}
