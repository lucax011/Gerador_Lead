from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Source(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    label: str
    channel: str
    base_score_multiplier: float = 0.5
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
