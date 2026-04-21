import logging
import re
from uuid import UUID

import httpx
from bs4 import BeautifulSoup

from services.scraper.sources.base import BaseSource, RawLead

logger = logging.getLogger(__name__)


class WebScraperSource(BaseSource):
    """Scrapes contact/lead information from a list of target URLs.

    Extracts structured data from HTML pages looking for common patterns:
    name+email combos, contact cards, table rows, etc.
    """

    EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")

    def __init__(
        self,
        urls: list[str],
        user_agent: str,
        niche_id: UUID | None = None,
        timeout: int = 15,
    ) -> None:
        self._urls = urls
        self._niche_id = niche_id
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )

    @property
    def source_name(self) -> str:
        return "web_scraping"

    async def fetch(self) -> list[RawLead]:
        results: list[RawLead] = []
        for url in self._urls:
            results.extend(await self._scrape_url(url))
        return results

    async def _scrape_url(self, url: str) -> list[RawLead]:
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch URL", extra={"url": url, "error": str(exc)})
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        leads: list[RawLead] = []

        for card in soup.select(".contact, .lead, .person, article, .card"):
            lead = self._extract_from_element(card, url)
            if lead:
                leads.append(lead)

        if not leads:
            leads.extend(self._extract_from_text(soup.get_text(), url))

        logger.info("Scraped leads", extra={"url": url, "count": len(leads)})
        return leads

    def _extract_from_element(self, element, source_url: str) -> RawLead | None:
        text = element.get_text(separator=" ", strip=True)
        emails = self.EMAIL_RE.findall(text)
        if not emails:
            return None
        phones = self.PHONE_RE.findall(text)
        return RawLead(
            name=self._guess_name(element) or "Unknown",
            email=emails[0],
            phone=phones[0].strip() if phones else None,
            company=self._guess_company(element),
            niche_id=self._niche_id,
            extra={"source_url": source_url},
        )

    def _extract_from_text(self, text: str, source_url: str) -> list[RawLead]:
        return [
            RawLead(
                name="Unknown",
                email=email,
                niche_id=self._niche_id,
                extra={"source_url": source_url},
            )
            for email in self.EMAIL_RE.findall(text)
        ]

    def _guess_name(self, element) -> str | None:
        for selector in ["h1", "h2", "h3", ".name", "[class*='name']", "strong"]:
            tag = element.select_one(selector)
            if tag:
                candidate = tag.get_text(strip=True)
                if 2 <= len(candidate) <= 100 and not self.EMAIL_RE.match(candidate):
                    return candidate
        return None

    def _guess_company(self, element) -> str | None:
        for selector in [".company", ".organization", "[class*='company']", "[class*='org']"]:
            tag = element.select_one(selector)
            if tag:
                return tag.get_text(strip=True)
        return None

    async def close(self) -> None:
        await self._client.aclose()
