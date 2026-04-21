"""Source Registry

Central place to register and retrieve lead sources.
Each source is identified by its source_name (matches LeadSource enum value).

Usage:
    registry = SourceRegistry()
    registry.register(WebScraperSource(urls=[...]))
    # registry.register(CsvSource(path="leads.csv"))   # future source
    # registry.register(ApiSource(endpoint="..."))      # future source

    for source in registry.all():
        leads = await source.fetch()
"""
import logging
from collections.abc import Iterator

from services.scraper.sources.base import BaseSource

logger = logging.getLogger(__name__)


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, BaseSource] = {}

    def register(self, source: BaseSource) -> None:
        if source.source_name in self._sources:
            raise ValueError(f"Source '{source.source_name}' already registered")
        self._sources[source.source_name] = source
        logger.info("Source registered", extra={"source": source.source_name})

    def get(self, name: str) -> BaseSource:
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not found in registry")
        return self._sources[name]

    def all(self) -> Iterator[BaseSource]:
        yield from self._sources.values()

    async def close_all(self) -> None:
        for source in self._sources.values():
            await source.close()
