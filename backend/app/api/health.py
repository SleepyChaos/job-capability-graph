from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    checked_at: datetime


@router.get("/health", response_model=HealthResponse)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok", checked_at=datetime.now(UTC))
