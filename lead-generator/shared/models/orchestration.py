from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OrchestrationDecision(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    # Decisões do orquestrador IA
    offer: str | None = None           # nichochat | consorcio | nenhuma
    approach: str | None = None        # whatsapp | instagram_dm | nurture | none
    tone: str | None = None            # direto | educativo | prova_social | urgencia
    best_time: str | None = None       # ex: "20h–22h"
    best_time_reason: str | None = None
    score_adjustment: float = 0.0      # ajuste fino sobre o score base
    final_score: float | None = None   # score_base + score_adjustment
    objections: list[str] = Field(default_factory=list)
    opening_message: str | None = None
    reasoning: str | None = None       # justificativa da IA em português
    model_used: str = "gpt-4o-mini"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    raw_response: dict[str, Any] = Field(default_factory=dict)


class OutreachAttempt(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    channel: str                       # whatsapp | instagram_dm | email
    status: str = "scheduled"          # scheduled | sent | delivered | read | failed
    message_text: str | None = None
    external_id: str | None = None    # ID da mensagem na Evolution API
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    error: str | None = None
    attempt_number: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
