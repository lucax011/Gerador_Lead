from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class RawLead:
    name: str
    email: str
    phone: str | None = None
    company: str | None = None
    niche_id: UUID | None = None
    extra: dict = field(default_factory=dict)


class BaseSource(ABC):
    """Contract that every lead source must implement.

    To add a new source:
    1. Create a file in services/scraper/sources/
    2. Subclass BaseSource and implement fetch()
    3. Register the instance in services/scraper/registry.py
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this source — must match the `name` column in the sources table."""

    @abstractmethod
    async def fetch(self) -> list[RawLead]:
        """Pull leads from the source and return raw, unvalidated data."""

    async def close(self) -> None:
        """Optional cleanup (close HTTP clients, DB cursors, etc.)."""
