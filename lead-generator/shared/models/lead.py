from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


class LeadStatus(str, Enum):
    CAPTURED = "captured"
    VALIDATED = "validated"
    DEDUPLICATED = "deduplicated"
    SCORED = "scored"
    DISTRIBUTED = "distributed"
    REJECTED = "rejected"


class Lead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    company: str | None = Field(default=None, max_length=255)
    source_id: UUID
    source_name: str
    status: LeadStatus = LeadStatus.CAPTURED
    score: float | None = None
    niche_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"use_enum_values": True}
