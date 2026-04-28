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
    created_at: datetime = Field(default_factory=datetime.utcnow)
