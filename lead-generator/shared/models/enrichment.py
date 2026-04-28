from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CNPJData(BaseModel):
    cnpj: str | None = None
    razao_social: str | None = None
    nome_fantasia: str | None = None
    atividade_principal: str | None = None
    natureza_juridica: str | None = None
    porte: str | None = None
    data_abertura: str | None = None
    situacao: str | None = None
    logradouro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    telefone: str | None = None
    email: str | None = None
    capital_social: float | None = None


class InstagramEnrichment(BaseModel):
    username: str | None = None
    followers: int | None = None
    following: int | None = None
    posts: int | None = None
    engagement_rate: float | None = None
    account_type: str | None = None
    bio: str | None = None
    profile_url: str | None = None
    has_business_email: bool = False
    has_whatsapp_in_bio: bool = False


class EnrichmentData(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    cnpj: CNPJData | None = None
    instagram: InstagramEnrichment | None = None
    # Stubs para integrações futuras (BigDataCorp, Serasa)
    bigdatacorp: dict[str, Any] = Field(default_factory=dict)
    serasa: dict[str, Any] = Field(default_factory=dict)
    facebook_capi: dict[str, Any] = Field(default_factory=dict)
    # Sinais derivados
    has_cnpj: bool = False
    estimated_revenue_tier: str | None = None  # micro / pequeno / medio / grande
    years_in_business: int | None = None
    sources_used: list[str] = Field(default_factory=list)
    enriched_at: datetime = Field(default_factory=datetime.utcnow)
