import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class RawLead:
    name: str
    email: str
    phone: str | None
    company: str | None
    source_url: str


class WebScraper:
    """Scrapes contact/lead information from target URLs.

    Extracts structured data from HTML pages looking for common patterns:
    name+email combos, contact cards, table rows, etc.
    """

    EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")

    def __init__(self, user_agent: str, timeout: int = 15) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )

    async def scrape(self, url: str) -> list[RawLead]:
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch URL", extra={"url": url, "error": str(exc)})
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        leads: list[RawLead] = []

        # Strategy 1: look for contact cards with class heuristics
        for card in soup.select(".contact, .lead, .person, article, .card"):
            lead = self._extract_from_element(card, url)
            if lead:
                leads.append(lead)

        # Strategy 2: scan plain text for email+name pairs when no cards found
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
        name = self._guess_name(element, text)
        company = self._guess_company(element, text)

        return RawLead(
            name=name or "Unknown",
            email=emails[0],
            phone=phones[0].strip() if phones else None,
            company=company,
            source_url=source_url,
        )

    def _extract_from_text(self, text: str, source_url: str) -> list[RawLead]:
        leads = []
        emails = self.EMAIL_RE.findall(text)
        for email in emails:
            leads.append(RawLead(name="Unknown", email=email, phone=None, company=None, source_url=source_url))
        return leads

    def _guess_name(self, element, text: str) -> str | None:
        for selector in ["h1", "h2", "h3", ".name", "[class*='name']", "strong"]:
            tag = element.select_one(selector)
            if tag:
                candidate = tag.get_text(strip=True)
                if 2 <= len(candidate) <= 100 and not self.EMAIL_RE.match(candidate):
                    return candidate
        return None

    def _guess_company(self, element, text: str) -> str | None:
        for selector in [".company", ".organization", "[class*='company']", "[class*='org']"]:
            tag = element.select_one(selector)
            if tag:
                return tag.get_text(strip=True)
        return None

    async def close(self) -> None:
        await self._client.aclose()
