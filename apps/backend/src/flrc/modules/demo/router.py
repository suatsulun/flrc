import secrets
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel

from flrc.config import settings
from flrc.modules.auth.demo import VISITOR_LIFETIME
from flrc.modules.demo import reset, schedule

router = APIRouter(tags=["demo"])


class DemoInfoOut(BaseModel):
    next_reset_at: datetime
    visitor_lifetime_hours: int
    state: Literal["ready", "resetting"]


@router.get("/demo")
async def demo_info() -> DemoInfoOut:
    """Public: lets the login page describe the demo before anyone signs in."""
    return DemoInfoOut(
        next_reset_at=schedule.next_reset_at(),
        visitor_lifetime_hours=int(VISITOR_LIFETIME.total_seconds() // 3600),
        state="resetting" if await reset.is_resetting() else "ready",
    )


async def require_ops_token(x_ops_token: Annotated[str, Header()] = "") -> None:
    if not x_ops_token or not secrets.compare_digest(x_ops_token, settings.ops_token):
        raise HTTPException(401, {"code": "ops_token_required"})


ops_router = APIRouter(prefix="/ops/demo", tags=["ops"], dependencies=[Depends(require_ops_token)])


class DemoResetStatusOut(BaseModel):
    state: Literal["idle", "resetting"]
    last_reset_date: str | None
    last_error: str | None
    next_reset_at: datetime
    due: bool


@ops_router.get("/status")
async def demo_reset_status() -> DemoResetStatusOut:
    return DemoResetStatusOut(**await reset.status())  # type: ignore[arg-type]


@ops_router.post("/reset", status_code=202)
async def request_demo_reset(background: BackgroundTasks) -> DemoResetStatusOut:
    """Start a reset in the background; poll the status route for completion."""
    if await reset.is_resetting():
        raise HTTPException(409, {"code": "demo_reset_in_progress"})
    background.add_task(reset.run_reset, reason="ops")
    return DemoResetStatusOut(**await reset.status())  # type: ignore[arg-type]
