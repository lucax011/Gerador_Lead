from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .lead import Lead


class BaseEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    lead: Lead


class LeadCapturedEvent(BaseEvent):
    event_type: str = "lead.captured"


class LeadValidatedEvent(BaseEvent):
    event_type: str = "lead.validated"
    validation_errors: list[str] = Field(default_factory=list)


class LeadDeduplicatedEvent(BaseEvent):
    event_type: str = "lead.deduplicated"
    is_duplicate: bool = False
    duplicate_of: UUID | None = None


class LeadEnrichedEvent(BaseEvent):
    event_type: str = "lead.enriched"
    enrichment: dict[str, Any] = Field(default_factory=dict)
    sources_used: list[str] = Field(default_factory=list)


class LeadScoredEvent(BaseEvent):
    event_type: str = "lead.scored"
    score: float
    temperature: str  # HOT | WARM | COLD
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    enrichment: dict[str, Any] = Field(default_factory=dict)
    niche_name: str | None = None  # nome legível do nicho para o orchestrator


class LeadOrchestratedEvent(BaseEvent):
    event_type: str = "lead.orchestrated"
    score: float
    temperature: str
    offer: str | None = None
    approach: str | None = None
    tone: str | None = None
    best_time: str | None = None
    objections: list[str] = Field(default_factory=list)
    opening_message: str | None = None
    final_score: float | None = None
