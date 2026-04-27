"""Enricher Worker

Consome lead.deduplicated, enriquece o perfil com dados externos e publica lead.enriched.

Fontes ativas:
  - CNPJ.ws (gratuito) — ativa automaticamente se lead tiver CNPJ no metadata
  - Instagram — re-usa dados já presentes no modelo (scraper Apify)

Fontes stub (ativar com credenciais no .env):
  - BigDataCorp — BIGDATACORP_TOKEN
  - Serasa Experian — SERASA_CLIENT_ID + SERASA_CLIENT_SECRET
  - Facebook CAPI — via services/distributor (futuro)
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4
from datetime import datetime

import structlog
from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQConsumer, RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import EnrichmentORM, LeadORM
from shared.database.session import AsyncSessionLocal
from shared.models.events import LeadEnrichedEvent
from shared.models.lead import Lead, LeadStatus
from services.enricher.sources.cnpjws import enrich_from_metadata, lookup_cnpj
from services.enricher.sources.bigdatacorp import enrich_company
from services.enricher.sources.serasa import get_credit_score

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher


def _extract_instagram_enrichment(lead: Lead) -> dict:
    """Consolida dados de Instagram já presentes no modelo."""
    if not lead.instagram_username:
        return {}
    ig = {
        "username": lead.instagram_username,
        "followers": lead.instagram_followers,
        "following": lead.instagram_following,
        "posts": lead.instagram_posts,
        "engagement_rate": lead.instagram_engagement_rate,
        "account_type": lead.instagram_account_type,
        "bio": lead.instagram_bio,
        "profile_url": lead.instagram_profile_url,
        "has_business_email": bool(
            lead.instagram_bio and ("@" in lead.instagram_bio or "email" in (lead.instagram_bio or "").lower())
        ),
        "has_whatsapp_in_bio": bool(
            lead.instagram_bio and ("whatsapp" in (lead.instagram_bio or "").lower() or "wpp" in (lead.instagram_bio or "").lower())
        ),
    }
    return {k: v for k, v in ig.items() if v is not None}


async def _enrich_cnpj(lead: Lead) -> dict | None:
    """Tenta enriquecer com CNPJ.ws se configurado e se houver CNPJ."""
    if not settings.cnpjws_enabled:
        return None

    # Tenta extrair CNPJ de metadata
    result = await enrich_from_metadata(lead.metadata)
    if result:
        log.info("CNPJ enriquecido via metadata", lead_id=str(lead.id), cnpj=result.get("cnpj", "")[:8] + "***")
        return result

    # Tenta pelo telefone convertido (alguns MEIs têm CNPJ derivado do CPF)
    # Sem CNPJ disponível, retorna None — sem chamada desnecessária
    return None


async def _persist_enrichment(lead: Lead, enrichment: dict, sources_used: list[str]) -> None:
    cnpj_data = enrichment.get("cnpj") or {}
    instagram_data = enrichment.get("instagram") or {}

    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(EnrichmentORM).where(EnrichmentORM.lead_id == lead.id)
        )
        enr_orm = existing.scalar_one_or_none()

        if enr_orm:
            enr_orm.cnpj_data = cnpj_data
            enr_orm.instagram_data = instagram_data
            enr_orm.has_cnpj = bool(cnpj_data.get("cnpj"))
            enr_orm.estimated_revenue_tier = cnpj_data.get("revenue_tier")
            enr_orm.years_in_business = cnpj_data.get("anos_atividade")
            enr_orm.sources_used = sources_used
            enr_orm.enriched_at = datetime.utcnow()
        else:
            enr_orm = EnrichmentORM(
                id=uuid4(),
                lead_id=lead.id,
                cnpj_data=cnpj_data,
                instagram_data=instagram_data,
                bigdatacorp_data={},
                serasa_data={},
                facebook_capi_data={},
                has_cnpj=bool(cnpj_data.get("cnpj")),
                estimated_revenue_tier=cnpj_data.get("revenue_tier"),
                years_in_business=cnpj_data.get("anos_atividade"),
                sources_used=sources_used,
                enriched_at=datetime.utcnow(),
            )
            session.add(enr_orm)

        await session.execute(
            update(LeadORM).where(LeadORM.id == lead.id).values(status=LeadStatus.ENRICHED)
        )
        await session.commit()


async def handle_lead_deduplicated(payload: dict[str, Any]) -> None:
    lead_data = payload["lead"]
    lead = Lead(**lead_data)
    log.info("Enriching lead", lead_id=str(lead.id), source=lead.source_name)

    enrichment: dict[str, Any] = {}
    sources_used: list[str] = []

    # 1. Instagram (re-usa dados já no modelo — sem custo de API)
    ig_data = _extract_instagram_enrichment(lead)
    if ig_data:
        enrichment["instagram"] = ig_data
        sources_used.append("instagram_model")

    # 2. CNPJ.ws (gratuito)
    cnpj_data = await _enrich_cnpj(lead)
    if cnpj_data:
        enrichment["cnpj"] = cnpj_data
        sources_used.append("cnpjws")

    # 3. BigDataCorp (stub — só roda se token configurado)
    if settings.bigdatacorp_token:
        cnpj_str = (cnpj_data or {}).get("cnpj", "")
        if cnpj_str:
            bdc = await enrich_company(cnpj_str, settings.bigdatacorp_token)
            if bdc.get("_status") != "stub":
                enrichment["bigdatacorp"] = bdc
                sources_used.append("bigdatacorp")

    # 4. Serasa (stub — só roda se credenciais configuradas)
    if settings.serasa_client_id and settings.serasa_client_secret:
        cpf = lead.metadata.get("cpf")
        if cpf:
            serasa = await get_credit_score(cpf, settings.serasa_client_id, settings.serasa_client_secret)
            if serasa.get("_status") != "stub":
                enrichment["serasa"] = serasa
                sources_used.append("serasa")

    if not sources_used:
        log.info("Sem dados de enriquecimento disponíveis — seguindo sem enriquecer", lead_id=str(lead.id))

    await _persist_enrichment(lead, enrichment, sources_used)

    # Propaga enrichment no payload para o Scorer usar
    event = LeadEnrichedEvent(
        lead=lead,
        enrichment=enrichment,
        sources_used=sources_used,
    )
    await publisher.publish("lead.enriched", event.model_dump(mode="json"))
    log.info("Published lead.enriched", lead_id=str(lead.id), sources=sources_used)


async def main() -> None:
    global publisher
    log.info("Enricher worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)

    await publisher.connect()
    await consumer.connect()
    log.info("Enricher conectado ao RabbitMQ")

    await consumer.consume(
        queue_name="enricher.lead.deduplicated",
        routing_key="lead.deduplicated",
        handler=handle_lead_deduplicated,
    )


if __name__ == "__main__":
    asyncio.run(main())
