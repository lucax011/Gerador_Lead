"""Scraper Worker

Periodically scrapes target URLs and publishes LeadCapturedEvent to RabbitMQ.
"""
import asyncio
import logging
import sys
from pathlib import Path

import structlog

# Allow imports from repo root when running as standalone
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQPublisher
from shared.config import get_settings
from shared.models.events import LeadCapturedEvent
from shared.models.lead import Lead, LeadSource, LeadStatus
from services.scraper.sources.web_scraper import WebScraper

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


async def scrape_and_publish(publisher: RabbitMQPublisher, scraper: WebScraper) -> None:
    for url in settings.scraper_urls_list:
        log.info("Scraping URL", url=url)
        raw_leads = await scraper.scrape(url)
        for raw in raw_leads:
            lead = Lead(
                name=raw.name,
                email=raw.email,
                phone=raw.phone,
                company=raw.company,
                source=LeadSource.WEB_SCRAPING,
                status=LeadStatus.CAPTURED,
                metadata={"source_url": raw.source_url},
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
    scraper = WebScraper(user_agent=settings.scraper_user_agent)

    await publisher.connect()
    log.info("Connected to RabbitMQ")

    try:
        while True:
            try:
                await scrape_and_publish(publisher, scraper)
            except Exception:
                log.exception("Error during scrape cycle")
            log.info("Sleeping until next cycle", seconds=settings.scraper_interval_seconds)
            await asyncio.sleep(settings.scraper_interval_seconds)
    finally:
        await scraper.close()
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
