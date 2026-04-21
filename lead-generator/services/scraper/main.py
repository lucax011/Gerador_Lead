"""Scraper Worker

Iterates all registered sources, collects RawLeads and publishes
LeadCapturedEvent to RabbitMQ. New sources are added via SourceRegistry
without touching this file.
"""
import asyncio
import logging
import sys
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQPublisher
from shared.config import get_settings
from shared.models.events import LeadCapturedEvent
from shared.models.lead import Lead, LeadSource, LeadStatus
from services.scraper.registry import SourceRegistry
from services.scraper.sources.web_scraper import WebScraperSource

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level)
    ),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)
log = structlog.get_logger(__name__)


def build_registry() -> SourceRegistry:
    """Register all active sources here.

    To activate a new source:
        1. Import its class
        2. Instantiate with its config
        3. Call registry.register(instance)
    """
    registry = SourceRegistry()

    if settings.scraper_urls_list:
        registry.register(
            WebScraperSource(
                urls=settings.scraper_urls_list,
                user_agent=settings.scraper_user_agent,
            )
        )

    # Future sources — uncomment when implemented:
    # registry.register(CsvSource(path=settings.csv_leads_path))
    # registry.register(ApiSource(endpoint=settings.api_leads_url, token=settings.api_token))
    # registry.register(LinkedInSource(cookie=settings.linkedin_cookie))

    return registry


async def run_cycle(publisher: RabbitMQPublisher, registry: SourceRegistry) -> None:
    for source in registry.all():
        log.info("Fetching from source", source=source.source_name)
        try:
            raw_leads = await source.fetch()
        except Exception:
            log.exception("Source fetch failed", source=source.source_name)
            continue

        for raw in raw_leads:
            lead = Lead(
                name=raw.name,
                email=raw.email,
                phone=raw.phone,
                company=raw.company,
                niche_id=raw.niche_id,
                source=LeadSource(source.source_name),
                status=LeadStatus.CAPTURED,
                metadata=raw.extra,
            )
            event = LeadCapturedEvent(lead=lead)
            try:
                await publisher.publish("lead.captured", event.model_dump(mode="json"))
                log.info("Published lead.captured", lead_id=str(lead.id), email=lead.email)
            except Exception:
                log.exception("Failed to publish lead", lead_id=str(lead.id))


async def main() -> None:
    log.info("Scraper worker starting")
    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    registry = build_registry()

    await publisher.connect()
    log.info("Connected to RabbitMQ", sources=len(list(registry.all())))

    try:
        while True:
            try:
                await run_cycle(publisher, registry)
            except Exception:
                log.exception("Error during scrape cycle")
            log.info("Sleeping until next cycle", seconds=settings.scraper_interval_seconds)
            await asyncio.sleep(settings.scraper_interval_seconds)
    finally:
        await registry.close_all()
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
