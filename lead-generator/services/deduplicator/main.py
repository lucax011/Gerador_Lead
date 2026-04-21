"""Deduplicator Worker

Consumes lead.validated, checks the database for duplicate emails,
publishes lead.deduplicated (or routes duplicate to dead-letter).
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQConsumer, RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import LeadORM
from shared.database.session import AsyncSessionLocal
from shared.models.events import LeadDeduplicatedEvent
from shared.models.lead import Lead, LeadStatus

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher


async def upsert_lead(lead: Lead) -> None:
    async with AsyncSessionLocal() as session:
        orm = LeadORM(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            company=lead.company,
            source=lead.source,
            status=lead.status,
            metadata_=lead.metadata,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )
        session.add(orm)
        await session.commit()


async def find_duplicate(email: str, current_id: UUID) -> UUID | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LeadORM).where(
                LeadORM.email == email.lower(),
                LeadORM.id != current_id,
            )
        )
        existing = result.scalar_one_or_none()
        return existing.id if existing else None


async def handle_lead_validated(payload: dict[str, Any]) -> None:
    lead_data = payload["lead"]
    lead = Lead(**lead_data)
    log.info("Deduplicating lead", lead_id=str(lead.id), email=lead.email)

    duplicate_id = await find_duplicate(lead.email, lead.id)

    if duplicate_id:
        log.warning("Duplicate lead detected", lead_id=str(lead.id), duplicate_of=str(duplicate_id))
        lead.status = LeadStatus.REJECTED
        event = LeadDeduplicatedEvent(lead=lead, is_duplicate=True, duplicate_of=duplicate_id)
        await publisher.publish_to_dead_letter(
            event.model_dump(mode="json"),
            reason=f"Duplicate of lead {duplicate_id}",
        )
        return

    lead.status = LeadStatus.DEDUPLICATED
    await upsert_lead(lead)

    event = LeadDeduplicatedEvent(lead=lead, is_duplicate=False)
    await publisher.publish("lead.deduplicated", event.model_dump(mode="json"))
    log.info("Published lead.deduplicated", lead_id=str(lead.id))


async def main() -> None:
    global publisher
    log.info("Deduplicator worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)

    await publisher.connect()
    await consumer.connect()
    log.info("Connected to RabbitMQ and PostgreSQL")

    await consumer.consume(
        queue_name="deduplicator.lead.validated",
        routing_key="lead.validated",
        handler=handle_lead_validated,
    )


if __name__ == "__main__":
    asyncio.run(main())
