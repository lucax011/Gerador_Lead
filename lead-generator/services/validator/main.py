"""Validator Worker

Consumes lead.captured, validates against business rules,
publishes lead.validated (or routes to dead-letter if invalid).
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQPublisher, RabbitMQConsumer
from shared.config import get_settings
from shared.models.events import LeadValidatedEvent
from shared.models.lead import Lead, LeadStatus
from services.validator.rules.business_rules import validate_lead

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher


async def handle_lead_captured(payload: dict[str, Any]) -> None:
    lead_data = payload["lead"]
    lead_id = lead_data.get("id", "?")
    log.info("Validating lead", lead_id=lead_id, email=lead_data.get("email"))

    errors = validate_lead(lead_data)

    lead = Lead(**lead_data)

    if errors:
        lead.status = LeadStatus.REJECTED
        log.warning("Lead rejected by validation", lead_id=lead_id, errors=errors)
        await publisher.publish_to_dead_letter(
            {"lead": lead.model_dump(mode="json"), "errors": errors},
            reason="; ".join(errors),
        )
        return

    lead.status = LeadStatus.VALIDATED
    event = LeadValidatedEvent(lead=lead, validation_errors=[])
    await publisher.publish("lead.validated", event.model_dump(mode="json"))
    log.info("Published lead.validated", lead_id=lead_id)


async def main() -> None:
    global publisher
    log.info("Validator worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)

    await publisher.connect()
    await consumer.connect()
    log.info("Connected to RabbitMQ")

    await consumer.consume(
        queue_name="validator.lead.captured",
        routing_key="lead.captured",
        handler=handle_lead_captured,
    )


if __name__ == "__main__":
    asyncio.run(main())
