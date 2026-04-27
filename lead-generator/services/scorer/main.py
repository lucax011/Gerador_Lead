"""Scorer Worker

Consumes lead.deduplicated, scores the lead 0-100,
and publishes lead.scored with temperature classification.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQConsumer, RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import LeadORM, NicheORM, ScoreORM, SourceORM
from shared.database.session import AsyncSessionLocal
from shared.models.events import LeadScoredEvent
from shared.models.lead import Lead, LeadStatus
from services.scorer.scoring_engine import ScoringEngine

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher
engine = ScoringEngine()

_source_multiplier_cache: dict[str, float] = {}
_niche_multiplier_cache: dict[str, float] = {}


async def get_source_multiplier(source_name: str) -> float:
    if source_name in _source_multiplier_cache:
        return _source_multiplier_cache[source_name]
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SourceORM).where(SourceORM.name == source_name))
        source_orm = result.scalar_one_or_none()
        multiplier = source_orm.base_score_multiplier if source_orm else 0.0
    _source_multiplier_cache[source_name] = multiplier
    return multiplier


_niche_name_cache: dict[str, str | None] = {}


async def get_niche_multiplier(niche_id) -> float:
    """Retorna o multiplier do nicho para o critério niche_match (0.0-1.0).
    Usa 0.5 (neutro) quando o lead não tem nicho atribuído.
    """
    if niche_id is None:
        return 0.5
    key = str(niche_id)
    if key in _niche_multiplier_cache:
        return _niche_multiplier_cache[key]
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(NicheORM).where(NicheORM.id == niche_id))
        niche_orm = result.scalar_one_or_none()
        multiplier = niche_orm.niche_score_multiplier if niche_orm else 0.5
        _niche_name_cache[key] = niche_orm.name if niche_orm else None
    _niche_multiplier_cache[key] = multiplier
    return multiplier


async def get_niche_name(niche_id) -> str | None:
    if niche_id is None:
        return None
    key = str(niche_id)
    if key in _niche_name_cache:
        return _niche_name_cache[key]
    await get_niche_multiplier(niche_id)
    return _niche_name_cache.get(key)


async def persist_score(lead: Lead, result) -> None:
    async with AsyncSessionLocal() as session:
        score_orm = ScoreORM(
            lead_id=lead.id,
            score=result.total,
            temperature=result.temperature,
            breakdown=result.breakdown,
        )
        session.add(score_orm)
        await session.execute(
            update(LeadORM).where(LeadORM.id == lead.id).values(status=LeadStatus.SCORED)
        )
        await session.commit()


async def handle_lead_enriched(payload: dict[str, Any]) -> None:
    lead_data = payload["lead"]
    lead = Lead(**lead_data)
    enrichment = payload.get("enrichment", {})
    log.info("Scoring lead", lead_id=str(lead.id), email=lead.email)

    source_multiplier = await get_source_multiplier(lead.source_name)
    niche_multiplier = await get_niche_multiplier(lead.niche_id)
    niche_name = await get_niche_name(lead.niche_id)
    result = engine.score(lead, source_multiplier, enrichment=enrichment, niche_multiplier=niche_multiplier)
    lead.status = LeadStatus.SCORED
    lead.score = result.total

    await persist_score(lead, result)

    event = LeadScoredEvent(
        lead=lead,
        score=result.total,
        temperature=result.temperature,
        score_breakdown=result.breakdown,
        enrichment=enrichment,
        niche_name=niche_name,
    )
    await publisher.publish("lead.scored", event.model_dump(mode="json"))
    log.info(
        "Published lead.scored",
        lead_id=str(lead.id),
        score=result.total,
        temperature=result.temperature,
    )


async def main() -> None:
    global publisher
    log.info("Scorer worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)

    await publisher.connect()
    await consumer.connect()
    log.info("Connected to RabbitMQ and PostgreSQL")

    await consumer.consume(
        queue_name="scorer.lead.enriched",
        routing_key="lead.enriched",
        handler=handle_lead_enriched,
    )


if __name__ == "__main__":
    asyncio.run(main())
