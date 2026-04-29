"""GooglePlacesSource

Captura leads via Google Places API (textSearch — nova API v1).
Source name: "google_maps" — deve existir na tabela sources com multiplier 0.9.

Ativação: definir GOOGLE_PLACES_API_KEY, GOOGLE_PLACES_SEARCH_TERMS e
GOOGLE_PLACES_LOCATION no .env.

A Places API retorna no máximo 20 resultados por chamada. Para gerar volume,
cada chamada a fetch() avança um termo da lista (round-robin). O loop contínuo
é controlado externamente pelo ciclo do worker (scraper_interval_seconds).

O email gerado é placeholder ({slug}@maps.import) — o scorer aplica −5 pts
automaticamente para sinalizar que deve ser enriquecido antes do contato.
"""
import logging
import re
import unicodedata

import httpx

from services.scraper.sources.base import BaseSource, RawLead

log = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.displayName,"
    "places.formattedAddress,"
    "places.internationalPhoneNumber,"
    "places.websiteUri,"
    "places.rating,"
    "places.userRatingCount,"
    "places.businessStatus"
)
_INSTAGRAM_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)")


class GooglePlacesSource(BaseSource):
    """Busca estabelecimentos no Google Places por termos de nicho e localização.

    Parâmetros:
        api_key        — chave Google Places API
        search_terms   — lista de termos (ex: ["nail", "manicure", "studio de unhas"])
        location       — localização como string (ex: "São Paulo, SP" ou "Campinas, SP, Alphaville")
    """

    def __init__(
        self,
        api_key: str,
        search_terms: list[str],
        location: str,
    ) -> None:
        self._api_key = api_key
        self._terms = search_terms
        self._location = location
        self._term_index = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def source_name(self) -> str:
        return "google_maps"

    async def fetch(self) -> list[RawLead]:
        if not self._terms:
            return []

        term = self._terms[self._term_index % len(self._terms)]
        self._term_index += 1

        try:
            return await self._search(term)
        except httpx.HTTPStatusError as exc:
            log.error("Google Places HTTP error", term=term, status=exc.response.status_code)
            return []
        except Exception:
            log.exception("Google Places fetch failed", term=term)
            return []

    async def _search(self, term: str) -> list[RawLead]:
        query = f"{term} {self._location}"
        resp = await self._client.post(
            PLACES_SEARCH_URL,
            headers={
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": FIELD_MASK,
                "Content-Type": "application/json",
            },
            json={
                "textQuery": query,
                "languageCode": "pt-BR",
                "regionCode": "BR",
                "maxResultCount": 20,
            },
        )
        resp.raise_for_status()

        places = resp.json().get("places", [])
        log.info("Google Places results", term=term, location=self._location, count=len(places))

        return [lead for place in places if (lead := self._place_to_raw_lead(place, term))]

    def _place_to_raw_lead(self, place: dict, search_tag: str) -> RawLead | None:
        name = (place.get("displayName") or {}).get("text", "").strip()
        if not name:
            return None

        phone = place.get("internationalPhoneNumber")
        address = place.get("formattedAddress", "")
        website = place.get("websiteUri", "")
        rating = place.get("rating")
        reviews = place.get("userRatingCount")
        business_status = place.get("businessStatus", "")

        # Email placeholder — scorer aplica −5 pts (sinal de enriquecimento pendente)
        email = f"{_slugify(name)}@maps.import"

        # Extrai Instagram se o websiteUri apontar para instagram.com
        instagram_username: str | None = None
        instagram_url: str | None = None
        if website:
            m = _INSTAGRAM_RE.search(website)
            if m:
                instagram_username = m.group(1).rstrip("/")
                instagram_url = f"https://www.instagram.com/{instagram_username}/"

        extra: dict = {
            "search_tag": search_tag,
            "address": address,
            "website": website,
            "rating": rating,
            "reviews": reviews,
            "business_status": business_status,
        }
        if instagram_username:
            extra["instagram_username"] = instagram_username
            extra["instagram_profile_url"] = instagram_url

        return RawLead(
            name=name,
            email=email,
            phone=phone,
            company=name,
            extra=extra,
        )

    async def close(self) -> None:
        await self._client.aclose()


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower())
    ascii_only = normalized.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", ".", ascii_only).strip(".")
