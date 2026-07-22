"""Dashboard summary endpoint — GET /dashboard."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardSummary)
async def get_dashboard(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DashboardSummary:
    """Home-page summary: devices protected, security score, today's
    incidents, recent threats, severity breakdown (architecture doc section 9)."""
    service = DashboardService(db)
    return await service.get_summary(current_user.id)
