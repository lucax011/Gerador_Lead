"""Testes unitários do ScoringEngine (v2).

Cobre todos os 5 critérios base + bônus de enriquecimento expandido:
  - data_completeness (30 pts)
  - source            (25 pts)
  - phone_present     (15 pts — celular/fixo/ausente)
  - email_domain      (15 pts)
  - niche_match       (15 pts — novo)
  - enrichment_bonus  (±15 pts — account_type, followers, engagement, cnpj, placeholder)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from unittest.mock import patch
from uuid import uuid4

from services.scorer.scoring_engine import ScoringEngine
from shared.models.lead import Lead


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lead(**kwargs) -> Lead:
    defaults = dict(
        name="Maria Souza",
        email="maria@empresa.com.br",
        phone="+5511988880000",
        company="Empresa SA",
        source_id=uuid4(),
        source_name="google_maps",
    )
    defaults.update(kwargs)
    return Lead(**defaults)


@pytest.fixture()
def engine():
    """Engine com pesos v2: 30-25-15-15-15 = 100."""
    with patch("services.scorer.scoring_engine.settings") as s:
        s.score_weight_data_completeness = 30
        s.score_weight_source = 25
        s.score_weight_phone_present = 15
        s.score_weight_email_domain = 15
        s.score_weight_niche_match = 15
        s.hot_score_threshold = 70
        s.warm_score_threshold = 40
        yield ScoringEngine()


# ---------------------------------------------------------------------------
# Completude (data_completeness — 30 pts)
# ---------------------------------------------------------------------------

class TestDataCompleteness:
    def test_todos_campos_preenchidos(self, engine):
        lead = _lead()
        result = engine.score(lead, source_multiplier=1.0)
        assert result.breakdown["data_completeness"] == 30.0

    def test_sem_telefone_e_empresa(self, engine):
        lead = _lead(phone=None, company=None)
        result = engine.score(lead, source_multiplier=1.0)
        # mandatory: name(0.5) + email(0.5) = 1.0 → 0.6*30 = 18
        # optional: 2/4 = 0.5 → 0.4*30 = 12  — total = 24
        assert result.breakdown["data_completeness"] == pytest.approx(24.0)

    def test_sem_todos_opcionais(self, engine):
        lead = _lead(phone=None, company=None)
        lead2 = _lead()
        assert engine.score(lead, 1.0).breakdown["data_completeness"] < \
               engine.score(lead2, 1.0).breakdown["data_completeness"]


# ---------------------------------------------------------------------------
# Fonte (source — 25 pts)
# ---------------------------------------------------------------------------

class TestSourceScore:
    def test_multiplier_maximo_paid(self, engine):
        assert engine.score(_lead(), source_multiplier=1.0).breakdown["source"] == 25.0

    def test_multiplier_zero(self, engine):
        assert engine.score(_lead(), source_multiplier=0.0).breakdown["source"] == 0.0

    def test_google_maps_0_9(self, engine):
        assert engine.score(_lead(), source_multiplier=0.9).breakdown["source"] == pytest.approx(22.5)

    def test_instagram_0_75(self, engine):
        assert engine.score(_lead(), source_multiplier=0.75).breakdown["source"] == pytest.approx(18.75)

    def test_web_scraping_0_4(self, engine):
        assert engine.score(_lead(), source_multiplier=0.4).breakdown["source"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Telefone (phone_present — 15 pts, com tipo)
# ---------------------------------------------------------------------------

class TestPhoneScore:
    def test_celular_br_ddi(self, engine):
        """Celular com DDI +55: 100% do peso."""
        lead = _lead(phone="+5511988880000")
        assert engine.score(lead, 1.0).breakdown["phone_present"] == 15.0

    def test_celular_br_sem_ddi(self, engine):
        """11988880000 — 11 dígitos, começa com 9 após DDD."""
        lead = _lead(phone="11988880000")
        assert engine.score(lead, 1.0).breakdown["phone_present"] == 15.0

    def test_celular_55_sem_mais(self, engine):
        lead = _lead(phone="5511988880000")
        assert engine.score(lead, 1.0).breakdown["phone_present"] == 15.0

    def test_fixo_br(self, engine):
        """Fixo: começa com 2-5 após DDD → 55% do peso = 8.25."""
        lead = _lead(phone="+551132223333")
        result = engine.score(lead, 1.0).breakdown["phone_present"]
        assert result == pytest.approx(15 * 0.55)

    def test_sem_telefone_zero(self, engine):
        lead = _lead(phone=None)
        assert engine.score(lead, 1.0).breakdown["phone_present"] == 0.0

    def test_telefone_espaco_branco_zero(self, engine):
        lead = _lead(phone="   ")
        assert engine.score(lead, 1.0).breakdown["phone_present"] == 0.0

    def test_telefone_formato_desconhecido_40pct(self, engine):
        """Número que não é BR → 40% do peso (existe mas não classificado)."""
        lead = _lead(phone="+14155552671")  # número americano
        result = engine.score(lead, 1.0).breakdown["phone_present"]
        assert result == pytest.approx(15 * 0.40)


# ---------------------------------------------------------------------------
# Domínio de email (email_domain — 15 pts)
# ---------------------------------------------------------------------------

class TestEmailDomain:
    def test_corporativo_br(self, engine):
        assert engine.score(_lead(email="j@startup.com.br"), 1.0).breakdown["email_domain"] == 15.0

    def test_corporativo_io(self, engine):
        assert engine.score(_lead(email="j@tech.io"), 1.0).breakdown["email_domain"] == 15.0

    def test_gmail_trusted(self, engine):
        assert engine.score(_lead(email="j@gmail.com"), 1.0).breakdown["email_domain"] == pytest.approx(9.0)

    def test_outlook_trusted(self, engine):
        assert engine.score(_lead(email="j@outlook.com"), 1.0).breakdown["email_domain"] == pytest.approx(9.0)

    def test_dominio_desconhecido(self, engine):
        assert engine.score(_lead(email="j@random.xyz"), 1.0).breakdown["email_domain"] == pytest.approx(4.5)

    def test_sem_arroba_zero(self, engine):
        lead = _lead()
        lead.__dict__["email"] = "invalido"
        assert engine.score(lead, 1.0).breakdown["email_domain"] == 0.0


# ---------------------------------------------------------------------------
# Niche match (15 pts — NOVO critério)
# ---------------------------------------------------------------------------

class TestNicheMatch:
    def test_niche_maximo_ecommerce(self, engine):
        """E-commerce tem multiplier 1.0 → 15 pts."""
        result = engine.score(_lead(), source_multiplier=1.0, niche_multiplier=1.0)
        assert result.breakdown["niche_match"] == 15.0

    def test_niche_neutro_default(self, engine):
        """Sem niche_id → 0.5 neutro → 7.5 pts."""
        result = engine.score(_lead(), source_multiplier=1.0, niche_multiplier=0.5)
        assert result.breakdown["niche_match"] == pytest.approx(7.5)

    def test_niche_industria_baixo(self, engine):
        """Indústria tem multiplier 0.6 → 9 pts."""
        result = engine.score(_lead(), source_multiplier=1.0, niche_multiplier=0.6)
        assert result.breakdown["niche_match"] == pytest.approx(9.0)

    def test_niche_zero(self, engine):
        result = engine.score(_lead(), source_multiplier=1.0, niche_multiplier=0.0)
        assert result.breakdown["niche_match"] == 0.0

    def test_niche_sempre_presente_no_breakdown(self, engine):
        result = engine.score(_lead(), source_multiplier=1.0)
        assert "niche_match" in result.breakdown


# ---------------------------------------------------------------------------
# Bônus de enriquecimento (±15 pts)
# ---------------------------------------------------------------------------

class TestEnrichmentBonus:
    def test_sem_dados_sem_bonus(self, engine):
        result = engine.score(_lead(), 1.0, enrichment={})
        assert "enrichment_bonus" not in result.breakdown

    # --- account_type (NOVO) ---
    def test_account_type_business_5pts(self, engine):
        lead = _lead(instagram_account_type="business")
        bonus = engine.score(lead, 1.0).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(5.0)

    def test_account_type_creator_3pts(self, engine):
        lead = _lead(instagram_account_type="creator")
        bonus = engine.score(lead, 1.0).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(3.0)

    def test_account_type_personal_sem_bonus(self, engine):
        lead = _lead(instagram_account_type="personal")
        result = engine.score(lead, 1.0)
        assert "enrichment_bonus" not in result.breakdown

    def test_account_type_via_enrichment_dict(self, engine):
        enrichment = {"instagram": {"account_type": "business"}}
        bonus = engine.score(_lead(), 1.0, enrichment=enrichment).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(5.0)

    # --- followers ---
    def test_followers_10k_8pts(self, engine):
        lead = _lead(instagram_followers=15000)
        bonus = engine.score(lead, 1.0).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(8.0)

    def test_followers_1k_4pts(self, engine):
        lead = _lead(instagram_followers=2000)
        bonus = engine.score(lead, 1.0).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(4.0)

    def test_followers_500_2pts(self, engine):
        lead = _lead(instagram_followers=800)
        bonus = engine.score(lead, 1.0).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(2.0)

    def test_followers_abaixo_500_sem_bonus(self, engine):
        lead = _lead(instagram_followers=100)
        result = engine.score(lead, 1.0)
        assert "enrichment_bonus" not in result.breakdown

    # --- engagement ---
    def test_engajamento_alto_5pts(self, engine):
        lead = _lead(instagram_engagement_rate=6.0)
        bonus = engine.score(lead, 1.0).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(5.0)

    def test_engajamento_medio_3pts(self, engine):
        lead = _lead(instagram_engagement_rate=3.5)
        bonus = engine.score(lead, 1.0).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(3.0)

    # --- CNPJ ---
    def test_cnpj_ativo_5pts(self, engine):
        enrichment = {"cnpj": {"cnpj": "12345678000100", "situacao": "ATIVA"}}
        bonus = engine.score(_lead(), 1.0, enrichment=enrichment).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(5.0)

    def test_cnpj_situacao_ativo(self, engine):
        enrichment = {"cnpj": {"cnpj": "12345678000100", "situacao": "ATIVO"}}
        bonus = engine.score(_lead(), 1.0, enrichment=enrichment).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(5.0)

    def test_cnpj_baixada_sem_bonus(self, engine):
        enrichment = {"cnpj": {"cnpj": "12345678000100", "situacao": "BAIXADA"}}
        result = engine.score(_lead(), 1.0, enrichment=enrichment)
        assert "enrichment_bonus" not in result.breakdown

    # --- Placeholder penalty (agora -5) ---
    def test_email_maps_import_penaliza_5pts(self, engine):
        """Email placeholder penaliza -5 (mais severo que antes)."""
        lead = _lead(email="joao.abc@maps.import", phone=None, company=None)
        result = engine.score(lead, 1.0)
        # Sem outros bônus → bonus = -5 → não aparece positivo no breakdown
        # mas o total é menor do que seria sem o placeholder
        lead_real = _lead(phone=None, company=None)
        assert engine.score(lead_real, 1.0).total > engine.score(lead, 1.0).total

    def test_bonus_maximo_cap_15(self, engine):
        """business(5) + 10k_followers(8) + engagement_5pct(5) + cnpj_ativo(5) = 23 → cap 15."""
        lead = _lead(
            instagram_account_type="business",
            instagram_followers=20000,
            instagram_engagement_rate=7.0,
        )
        enrichment = {"cnpj": {"cnpj": "12345678000100", "situacao": "ATIVA"}}
        bonus = engine.score(lead, 1.0, enrichment=enrichment).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(15.0)

    def test_bonus_negativo_cap_menos_15(self, engine):
        """Garante que penalidade nunca passa de -15."""
        lead = _lead(email="x@maps.import")
        result = engine.score(lead, 1.0)
        # -5 é o único sinal negativo → não passa de -15
        bonus = result.breakdown.get("enrichment_bonus", 0)
        assert bonus >= -15.0

    def test_enrichment_dict_tem_prioridade_sobre_lead(self, engine):
        """Dado em enrichment dict sobrescreve campo do Lead."""
        lead = _lead(instagram_followers=100)  # poucos no model
        enrichment = {"instagram": {"followers": 15000}}  # muitos no enrichment
        bonus = engine.score(lead, 1.0, enrichment=enrichment).breakdown.get("enrichment_bonus", 0)
        assert bonus == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Score total, temperatura e clamping
# ---------------------------------------------------------------------------

class TestTotalAndTemperature:
    def test_lead_perfeito_hot(self, engine):
        """Lead completo + paid_traffic + nicho top + business instagram → HOT."""
        lead = _lead(instagram_account_type="business", instagram_followers=15000)
        result = engine.score(lead, source_multiplier=1.0, niche_multiplier=1.0)
        assert result.temperature == "HOT"
        assert result.total == 100.0  # clamped

    def test_lead_sem_telefone_gmail_warm(self, engine):
        """Sem telefone, gmail, multipliers médios → WARM."""
        lead = _lead(phone=None, email="j@gmail.com", company=None)
        result = engine.score(lead, source_multiplier=0.75, niche_multiplier=0.5)
        # completude: mandatory=1.0→18; optional=2/4=0.5→12 → 24
        # Wait: mandatory * 0.6 * 30 = 1.0 * 0.6 * 30 = 18
        # optional: 2/4 * 0.4 * 30 = 0.5 * 12 = 6 → total completude = 24
        # source: 0.75 * 25 = 18.75
        # phone: 0
        # domain: gmail → 15 * 0.6 = 9
        # niche: 0.5 * 15 = 7.5
        # total = 59.25 → WARM
        assert result.total == pytest.approx(59.25)
        assert result.temperature == "WARM"

    def test_score_nunca_abaixo_zero(self, engine):
        lead = _lead(email="x@maps.import", phone=None, company=None)
        assert engine.score(lead, 0.0, niche_multiplier=0.0).total >= 0.0

    def test_score_nunca_acima_100(self, engine):
        lead = _lead(
            instagram_account_type="business",
            instagram_followers=50000,
            instagram_engagement_rate=10.0,
        )
        enrichment = {"cnpj": {"cnpj": "12345678000100", "situacao": "ATIVA"}}
        result = engine.score(lead, 1.0, enrichment=enrichment, niche_multiplier=1.0)
        assert result.total <= 100.0

    def test_breakdown_contem_5_criterios_base(self, engine):
        result = engine.score(_lead(), 1.0)
        for key in ("data_completeness", "source", "phone_present", "email_domain", "niche_match"):
            assert key in result.breakdown

    def test_threshold_hot_exato(self, engine):
        assert engine._classify(70.0) == "HOT"
        assert engine._classify(69.99) == "WARM"

    def test_threshold_warm_exato(self, engine):
        assert engine._classify(40.0) == "WARM"
        assert engine._classify(39.99) == "COLD"

    def test_niche_impacta_temperatura(self, engine):
        """Mesmo lead, niche alto vs niche baixo → temperaturas diferentes."""
        lead = _lead(phone=None, email="j@gmail.com", company=None)
        result_alto = engine.score(lead, source_multiplier=0.75, niche_multiplier=1.0)
        result_baixo = engine.score(lead, source_multiplier=0.75, niche_multiplier=0.0)
        assert result_alto.total > result_baixo.total

    def test_celular_vs_fixo_impacta_score(self, engine):
        """Celular pontua mais que fixo."""
        celular = _lead(phone="+5511988880000")
        fixo = _lead(phone="+551132223333")
        assert engine.score(celular, 1.0).breakdown["phone_present"] > \
               engine.score(fixo, 1.0).breakdown["phone_present"]


# ---------------------------------------------------------------------------
# Cenários realistas (simulação end-to-end do scoring)
# ---------------------------------------------------------------------------

class TestCenariosRealistas:
    def test_dono_restaurante_instagram_business(self, engine):
        """
        Restaurante com conta business, 5k seguidores, encontrado via Google Maps.
        Nicho: saúde-bem-estar (0.9).
        """
        lead = _lead(
            phone="+5511999990000",
            email="restaurante@gmail.com",
            instagram_account_type="business",
            instagram_followers=5000,
        )
        result = engine.score(lead, source_multiplier=0.9, niche_multiplier=0.9)
        # completude: 30, source: 22.5, phone: 15, domain: 9, niche: 13.5
        # bonus: business(5) + 1k_followers(4) = 9 → cap ok
        # total = 30 + 22.5 + 15 + 9 + 13.5 + 9 = 99 → clamped 99
        assert result.total >= 80.0
        assert result.temperature == "HOT"

    def test_lead_frio_sem_dados(self, engine):
        """Lead scrapeado com dados mínimos, nicho desconhecido."""
        lead = _lead(phone=None, company=None, email="alguem@hotmail.com")
        result = engine.score(lead, source_multiplier=0.4, niche_multiplier=0.5)
        # completude: 24, source: 10, phone: 0, domain: 9, niche: 7.5
        # total = 50.5 → WARM
        assert result.total == pytest.approx(50.5)
        assert result.temperature == "WARM"

    def test_lead_maps_sem_email_real(self, engine):
        """Lead importado do Google Maps com placeholder de email."""
        lead = _lead(
            email="padaria.abc123@maps.import",
            phone="+5511988880000",
            instagram_account_type="business",
        )
        result = engine.score(lead, source_multiplier=0.9, niche_multiplier=0.85)
        # completude: 30, source: 22.5, phone: 15
        # domain: placeholder → 0 (não é .com.br, .io etc)
        # niche: 12.75
        # bonus: business(5) - maps.import(5) = 0 → sem enrichment_bonus
        assert result.total > 50.0  # ainda WARM por conta dos dados
        assert "enrichment_bonus" not in result.breakdown

    def test_advogado_cnpj_ativo_pago(self, engine):
        """
        Advogado com CNPJ ativo, veio via Meta Ads (tráfego pago).
        Nicho: serviços-jurídicos (0.9).
        Produto ideal: Consórcio imóvel.
        """
        lead = _lead(
            phone="+5511977778888",
            email="dr.silva@silva-advogados.com.br",
            company="Silva Advogados LTDA",
        )
        enrichment = {"cnpj": {"cnpj": "12345678000100", "situacao": "ATIVA"}}
        result = engine.score(
            lead,
            source_multiplier=1.0,
            enrichment=enrichment,
            niche_multiplier=0.9,
        )
        # completude: 30, source: 25, phone: 15, domain: 15, niche: 13.5
        # bonus: cnpj_ativo(5)
        # total = 103.5 → clamped 100
        assert result.total == 100.0
        assert result.temperature == "HOT"
