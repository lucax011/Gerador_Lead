from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CampaignORM(Base):
    __tablename__ = "campanhas"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Campos de oferta legados (single-offer) — mantidos para retrocompatibilidade
    offer_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ideal_customer_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    focus_segments: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Multi-offer (0003_multi_offer): cada item {slug, description, icp, ticket}
    offers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    offer_operator: Mapped[str] = mapped_column(String(3), nullable=False, default="OR")
    compatibility_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    max_leads_per_sweep: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    # Pré-filtro semântico do sweep (0005_ai_tagger): interseção com lead.tags
    keywords_alvo: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    leads: Mapped[list["LeadORM"]] = relationship("LeadORM", back_populates="campanha")


class NicheORM(Base):
    __tablename__ = "niches"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    niche_score_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    leads: Mapped[list["LeadORM"]] = relationship("LeadORM", back_populates="niche")


class SourceORM(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    base_score_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    leads: Mapped[list["LeadORM"]] = relationship("LeadORM", back_populates="source_rel")


class LeadORM(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    campanha_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campanhas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="captured")
    niche_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("niches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Instagram public profile (populated by ApifyInstagramSource or enricher stage)
    instagram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instagram_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram_followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instagram_following: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instagram_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instagram_engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    instagram_account_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    instagram_profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    # Tags semânticas geradas pelo AI Tagger (0005_ai_tagger)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    perfil_resumido: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Histórico de análises por oferta — cada item: {offer_slug, score, channel, tone, time, reason, insufficient_data}
    offer_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    campanha: Mapped["CampaignORM | None"] = relationship("CampaignORM", back_populates="leads")
    niche: Mapped["NicheORM | None"] = relationship("NicheORM", back_populates="leads")
    source_rel: Mapped["SourceORM"] = relationship("SourceORM", back_populates="leads")
    scores: Mapped[list["ScoreORM"]] = relationship("ScoreORM", back_populates="lead", cascade="all, delete-orphan")
    enrichment: Mapped["EnrichmentORM | None"] = relationship("EnrichmentORM", back_populates="lead", uselist=False, cascade="all, delete-orphan")
    orchestrations: Mapped[list["OrchestrationORM"]] = relationship("OrchestrationORM", back_populates="lead", cascade="all, delete-orphan")
    outreach_attempts: Mapped[list["OutreachAttemptORM"]] = relationship("OutreachAttemptORM", back_populates="lead", cascade="all, delete-orphan")


class ScoreORM(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[str] = mapped_column(String(10), nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead: Mapped["LeadORM"] = relationship("LeadORM", back_populates="scores")


class EnrichmentORM(Base):
    __tablename__ = "enrichments"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    cnpj_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    instagram_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    bigdatacorp_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    serasa_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    facebook_capi_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    has_cnpj: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estimated_revenue_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    years_in_business: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sources_used: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    enriched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    lead: Mapped["LeadORM"] = relationship("LeadORM", back_populates="enrichment")


class OrchestrationORM(Base):
    __tablename__ = "orchestration_decisions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    need_identified: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    approach: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    best_time: Mapped[str | None] = mapped_column(String(30), nullable=True)
    best_time_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    objections: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    opening_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str] = mapped_column(String(50), nullable=False, default="gpt-4o-mini")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    lead: Mapped["LeadORM"] = relationship("LeadORM", back_populates="orchestrations")


class OutreachAttemptORM(Base):
    __tablename__ = "outreach_attempts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    lead: Mapped["LeadORM"] = relationship("LeadORM", back_populates="outreach_attempts")


class SweepJobORM(Base):
    __tablename__ = "sweep_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    campanha_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campanhas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campanha_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compatible: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    insufficient: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    operator: Mapped[str] = mapped_column(String(3), nullable=False, default="OR")
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    offers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
