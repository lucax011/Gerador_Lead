from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CampaignStatus(str):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    FINISHED = "finished"


class Campaign(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    status: str = "draft"
    objective: str | None = None
    source_config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    # Campos de oferta — usados pelo orquestrador em modo varredura
    offer_description: str | None = None
    ideal_customer_profile: str | None = None
    ticket: str | None = None
    focus_segments: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
