from dataclasses import dataclass

from shared.config import get_settings
from shared.models.lead import Lead

settings = get_settings()

TRUSTED_DOMAINS = frozenset(
    {
        "gmail.com", "outlook.com", "hotmail.com", "yahoo.com",
        "icloud.com", "protonmail.com", "live.com",
    }
)

CORPORATE_DOMAIN_PATTERNS = (
    ".com.br", ".com", ".io", ".co",
)


@dataclass
class ScoreResult:
    total: float
    temperature: str
    breakdown: dict[str, float]


class ScoringEngine:
    """Scores leads 0-100 using configurable weights.

    Criteria:
    - data_completeness (default 40 pts): all core fields present & non-empty
    - source             (default 25 pts): driven by source.base_score_multiplier from DB
    - phone_present      (default 20 pts): phone number provided
    - email_domain       (default 15 pts): corporate or trusted domain
    """

    def __init__(self) -> None:
        self.w_completeness = settings.score_weight_data_completeness
        self.w_source = settings.score_weight_source
        self.w_phone = settings.score_weight_phone_present
        self.w_domain = settings.score_weight_email_domain

    def score(self, lead: Lead, source_multiplier: float) -> ScoreResult:
        breakdown: dict[str, float] = {}

        breakdown["data_completeness"] = self._score_completeness(lead)
        breakdown["source"] = round(source_multiplier * self.w_source, 2)
        breakdown["phone_present"] = self._score_phone(lead)
        breakdown["email_domain"] = self._score_domain(lead)

        total = sum(breakdown.values())
        total = round(min(max(total, 0.0), 100.0), 2)

        temperature = self._classify(total)
        return ScoreResult(total=total, temperature=temperature, breakdown=breakdown)

    def _score_completeness(self, lead: Lead) -> float:
        fields = [lead.name, lead.email, lead.phone, lead.company]
        filled = sum(1 for f in fields if f and str(f).strip())
        mandatory_score = (1.0 if lead.name else 0) * 0.5 + (1.0 if lead.email else 0) * 0.5
        optional_score = filled / len(fields)
        raw = mandatory_score * 0.6 + optional_score * 0.4
        return round(raw * self.w_completeness, 2)

    def _score_phone(self, lead: Lead) -> float:
        return float(self.w_phone) if lead.phone and lead.phone.strip() else 0.0

    def _score_domain(self, lead: Lead) -> float:
        if not lead.email or "@" not in lead.email:
            return 0.0
        domain = lead.email.split("@")[-1].lower()
        if domain in TRUSTED_DOMAINS:
            return round(self.w_domain * 0.6, 2)
        if any(domain.endswith(p) for p in CORPORATE_DOMAIN_PATTERNS) and "." in domain:
            return round(self.w_domain * 1.0, 2)
        return round(self.w_domain * 0.3, 2)

    def _classify(self, score: float) -> str:
        if score >= settings.hot_score_threshold:
            return "HOT"
        if score >= settings.warm_score_threshold:
            return "WARM"
        return "COLD"
