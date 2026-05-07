"""AI co-pilot — conversational audit assistant endpoint."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import User
from app.schemas import CopilotRequest, CopilotResponse

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("", response_model=CopilotResponse)
async def chat(
    payload: CopilotRequest,
    org_id: Annotated[UUID, Depends(get_org_id)],
    _: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    from app.ai.copilot import run_copilot
    return await run_copilot(
        message=payload.message,
        org_id=org_id,
        db=db,
        context_risk_id=payload.context_risk_id,
        context_control_id=payload.context_control_id,
        context_plan_id=payload.context_plan_id,
        conversation_history=payload.conversation_history,
    )


@router.post("/interview-guide")
async def generate_interview_guide(
    risk_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    from app.ai.copilot import generate_interview_guide
    guide = await generate_interview_guide(risk_id=risk_id, org_id=org_id, db=db)
    return {"guide": guide}
