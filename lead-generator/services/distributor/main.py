"""Distributor Worker

Consumes lead.scored, routes by temperature, and delivers via Telegram.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import update

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQConsumer, RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import LeadORM
from shared.database.session import AsyncSessionLocal
from shared.models.lead import Lead, LeadStatus
from services.distributor.channels.telegram import TelegramChannel

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher
telegram: TelegramChannel


async def mark_distributed(lead_id) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(LeadORM).where(LeadORM.id == lead_id).values(status=LeadStatus.DISTRIBUTED)
        )
        await session.commit()


async def handle_lead_scored(payload: dict[str, Any]) -> None:
    lead_data = payload["lead"]
    score = payload["score"]
    temperature = payload["temperature"]
    lead = Lead(**lead_data)

    log.info(
        "Distributing lead",
        lead_id=str(lead.id),
        score=score,
        temperature=temperature,
    )

    sent = await telegram.send(lead_data, score, temperature)

    if sent:
        lead.status = LeadStatus.DISTRIBUTED
        await mark_distributed(lead.id)
        log.info("Lead distributed via Telegram", lead_id=str(lead.id), temperature=temperature)
    else:
        log.error("Distribution failed — routing to dead-letter", lead_id=str(lead.id))
        await publisher.publish_to_dead_letter(
            payload,
            reason="Telegram delivery failed",
        )


async def main() -> None:
    global publisher, telegram
    log.info("Distributor worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)
    telegram = TelegramChannel(
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    await publisher.connect()
    await consumer.connect()
    log.info("Connected to RabbitMQ, PostgreSQL, and Telegram")

    try:
        await consumer.consume(
            queue_name="distributor.lead.scored",
            routing_key="lead.scored",
            handler=handle_lead_scored,
        )
    finally:
        await telegram.close()
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
