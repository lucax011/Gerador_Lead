"""ScoringEngine — qualificação de leads 0-100.

Critérios (pesos somam 100 pts base):
  data_completeness  30 pts  — campos obrigatórios e opcionais preenchidos
  source             25 pts  — intenção inferida pela origem (multiplier da tabela sources)
  phone_present      15 pts  — celular > fixo > ausente (proxy de acessibilidade)
  email_domain       15 pts  — domínio corporativo > pessoal > desconhecido
  niche_match        15 pts  — aderência do segmento aos produtos ofertados

Bônus de enriquecimento (até +15 pts, não rompe escala):
  instagram_account_type:  business=+5, creator=+3
  instagram_followers:     10k+=+8, 1k+=+4, 500+=+2
  engagement_rate:         5%+=+5, 3%+=+3
  cnpj_ativo:              +5
  penalidade placeholder:  email @maps.import = -5
"""
import re
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

CORPORATE_DOMAIN_PATTERNS = (".com.br", ".com", ".io", ".co")

# Celular brasileiro: +55 + DDD (2 dígitos) + 9 + 8 dígitos = 13 dígitos totais (sem +)
# Padrão: começa com 55, DDD válido, nono dígito = 9
_BR_MOBILE_RE = re.compile(r"^(?:\+?55)?(\d{2})9\d{8}$")
_BR_LANDLINE_RE = re.compile(r"^(?:\+?55)?(\d{2})[2-5]\d{7}$")


@dataclass
class ScoreResult:
    total: float
    temperature: str
    breakdown: dict[str, float]


class ScoringEngine:
    """Scores leads 0–100 com 5 critérios + bônus de enriquecimento.

    Critérios base (somam 100 pts):
      data_completeness  30 pts
      source             25 pts  — via source.base_score_multiplier
      phone_present      15 pts  — celular=100%, fixo=55%, ausente=0%
      email_domain       15 pts  — corporativo=100%, trusted=60%, outros=30%
      niche_match        15 pts  — via niche.niche_score_multiplier

    Bônus (até +15 pts, capped):
      account_type, followers, engajamento, CNPJ, placeholder penalty
    """

    def __init__(self) -> None:
        self.w_completeness = settings.score_weight_data_completeness
        self.w_source = settings.score_weight_source
        self.w_phone = settings.score_weight_phone_present
        self.w_domain = settings.score_weight_email_domain
        self.w_niche = settings.score_weight_niche_match

    def score(
        self,
        lead: Lead,
        source_multiplier: float,
        enrichment: dict | None = None,
        niche_multiplier: float = 0.5,
    ) -> ScoreResult:
        enrichment = enrichment or {}
        breakdown: dict[str, float] = {}

        breakdown["data_completeness"] = self._score_completeness(lead)
        breakdown["source"] = round(source_multiplier * self.w_source, 2)
        breakdown["phone_present"] = self._score_phone(lead)
        breakdown["email_domain"] = self._score_domain(lead)
        breakdown["niche_match"] = round(niche_multiplier * self.w_niche, 2)

        bonus = self._score_enrichment_bonus(lead, enrichment)
        if bonus != 0:
            breakdown["enrichment_bonus"] = bonus

        total = sum(breakdown.values())
        total = round(min(max(total, 0.0), 100.0), 2)
        return ScoreResult(total=total, temperature=self._classify(total), breakdown=breakdown)

    # ------------------------------------------------------------------
    # Critérios base
    # ------------------------------------------------------------------

    def _score_completeness(self, lead: Lead) -> float:
        """
        Mandatory (60% do peso): name + email — lead sem um deles é inútil.
        Optional  (40% do peso): phone + company — sinalizam perfil mais rico.
        """
        mandatory = (
            (0.5 if lead.name and lead.name.strip() else 0.0)
            + (0.5 if lead.email else 0.0)
        )
        fields = [lead.name, lead.email, lead.phone, lead.company]
        optional = sum(1 for f in fields if f and str(f).strip()) / len(fields)
        raw = mandatory * 0.6 + optional * 0.4
        return round(raw * self.w_completeness, 2)

    def _score_phone(self, lead: Lead) -> float:
        """
        Celular BR → 100% do peso  (acessível via WhatsApp)
        Fixo BR    →  55% do peso  (alcançável, mas menos eficaz)
        Ausente    →   0%
        Formato não identificado → 40% (existe mas não foi possível classificar)
        """
        phone = (lead.phone or "").strip()
        if not phone:
            return 0.0
        digits = re.sub(r"\D", "", phone)
        if _BR_MOBILE_RE.match(digits):
            return float(self.w_phone)
        if _BR_LANDLINE_RE.match(digits):
            return round(self.w_phone * 0.55, 2)
        return round(self.w_phone * 0.40, 2)

    def _score_domain(self, lead: Lead) -> float:
        if not lead.email or "@" not in lead.email:
            return 0.0
        domain = lead.email.split("@")[-1].lower()
        if domain in TRUSTED_DOMAINS:
            return round(self.w_domain * 0.6, 2)
        if any(domain.endswith(p) for p in CORPORATE_DOMAIN_PATTERNS) and "." in domain:
            return round(self.w_domain * 1.0, 2)
        return round(self.w_domain * 0.3, 2)

    # ------------------------------------------------------------------
    # Bônus de enriquecimento
    # ------------------------------------------------------------------

    def _score_enrichment_bonus(self, lead: Lead, enrichment: dict) -> float:
        """
        Bônus baseado em dados coletados pelo Enricher.
        Cap em ±15 pts para não inflar artificialmente a escala base.

        Sinal           Fonte           Lógica de negócio
        ─────────────── ─────────────── ──────────────────────────────────────
        account_type    Instagram       conta business = autoridade decisória
        followers       Instagram       audiência = prova de mercado
        engagement_rate Instagram       audiência ativa > audiência grande
        cnpj_ativo      CNPJ.ws         empresa real e operante
        placeholder     API             lead sem email verdadeiro = má qualidade
        """
        bonus = 0.0
        ig = enrichment.get("instagram") or {}
        cnpj = enrichment.get("cnpj") or {}

        # Tipo de conta Instagram — proxy de autoridade decisória (BANT: Authority)
        account_type = ig.get("account_type") or lead.instagram_account_type or ""
        if account_type == "business":
            bonus += 5.0
        elif account_type == "creator":
            bonus += 3.0

        # Seguidores — prova de audiência real (maior = mais valioso como parceiro)
        followers = ig.get("followers") or lead.instagram_followers or 0
        if followers >= 10_000:
            bonus += 8.0
        elif followers >= 1_000:
            bonus += 4.0
        elif followers >= 500:
            bonus += 2.0

        # Engajamento — audiência ativa supera audiência grande comprada
        engagement = ig.get("engagement_rate") or lead.instagram_engagement_rate or 0
        if engagement >= 5.0:
            bonus += 5.0
        elif engagement >= 3.0:
            bonus += 3.0

        # CNPJ ativo — empresa real, mais propensa a pagar mensalidade (BANT: Budget)
        if cnpj.get("cnpj") and cnpj.get("situacao", "").upper() in ("ATIVA", "ATIVO"):
            bonus += 5.0

        # Email placeholder = lead sem email real → penalidade maior que antes
        # Justificativa: não conseguimos contactar esse lead por email de jeito nenhum
        if lead.email and lead.email.endswith("@maps.import"):
            bonus -= 5.0

        return round(min(max(bonus, -15.0), 15.0), 2)

    # ------------------------------------------------------------------
    # Temperatura
    # ------------------------------------------------------------------

    def _classify(self, score: float) -> str:
        if score >= settings.hot_score_threshold:
            return "HOT"
        if score >= settings.warm_score_threshold:
            return "WARM"
        return "COLD"
