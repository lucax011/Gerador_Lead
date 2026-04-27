"""Tests for niche_classifier — pure function, zero mocks needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.enricher.sources.niche_classifier import classify_niche, _normalize


# ---------------------------------------------------------------------------
# _normalize helper
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("CABELEIREIROS") == "cabeleireiros"

    def test_strip_accents(self):
        assert _normalize("Estética") == "estetica"
        assert _normalize("Odontológico") == "odontologico"
        assert _normalize("Construção") == "construcao"

    def test_collapses_whitespace(self):
        assert _normalize("  salão  de  beleza  ") == "salao de beleza"


# ---------------------------------------------------------------------------
# Beleza e Estética
# ---------------------------------------------------------------------------

class TestBelezaEstetica:
    def test_cnpj_cabeleireiros(self):
        assert classify_niche(atividade="Cabeleireiros, manicures e pedicures") == "beleza-estetica"

    def test_cnpj_estetica(self):
        assert classify_niche(atividade="Atividades de estética e outros serviços de cuidados com a beleza") == "beleza-estetica"

    def test_bio_nail_designer(self):
        assert classify_niche(bio="Nail designer 💅 São Paulo | agenda aberta") == "beleza-estetica"

    def test_bio_lash(self):
        assert classify_niche(bio="Lash designer ✨ alongamento fio a fio") == "beleza-estetica"

    def test_bio_sobrancelha(self):
        assert classify_niche(bio="Design de sobrancelha e micropigmentação") == "beleza-estetica"

    def test_company_studio(self):
        assert classify_niche(company="Studio Glow Estética Ltda") == "beleza-estetica"

    def test_source_hint_instagram(self):
        # source hint só quando zero sinais textuais
        assert classify_niche(source_name="instagram") == "beleza-estetica"


# ---------------------------------------------------------------------------
# Academia e Fitness
# ---------------------------------------------------------------------------

class TestAcademiaFitness:
    def test_cnpj_academia(self):
        assert classify_niche(atividade="Academias de condicionamento físico") == "academia-fitness"

    def test_bio_personal_trainer(self):
        assert classify_niche(bio="Personal trainer 💪 | treinos online e presenciais") == "academia-fitness"

    def test_bio_pilates(self):
        assert classify_niche(bio="Estúdio de pilates em BH 🧘") == "academia-fitness"

    def test_bio_crossfit(self):
        assert classify_niche(bio="Coach CrossFit | emagrecimento e performance") == "academia-fitness"


# ---------------------------------------------------------------------------
# Saúde e Bem-estar
# ---------------------------------------------------------------------------

class TestSaudeBemEstar:
    def test_cnpj_clinica(self):
        assert classify_niche(atividade="Clínicas e residências médicas") == "saude-bem-estar"

    def test_cnpj_nutricao(self):
        assert classify_niche(atividade="Atividades de nutrição e dietética") == "saude-bem-estar"

    def test_cnpj_psicologia(self):
        assert classify_niche(atividade="Atividades de psicologia e psicanálise") == "saude-bem-estar"

    def test_bio_terapeuta(self):
        assert classify_niche(bio="Terapeuta holística | terapia integrativa") == "saude-bem-estar"

    def test_cnpj_odontologia(self):
        assert classify_niche(atividade="Odontologia") == "saude-bem-estar"


# ---------------------------------------------------------------------------
# Alimentação
# ---------------------------------------------------------------------------

class TestAlimentacao:
    def test_cnpj_restaurante(self):
        assert classify_niche(atividade="Restaurantes e similares") == "alimentacao"

    def test_cnpj_padaria(self):
        assert classify_niche(atividade="Fabricação de pães, biscoitos e bolos") == "alimentacao"

    def test_bio_delivery(self):
        assert classify_niche(bio="Marmita fitness delivery | SP 🥗 pedidos via WhatsApp") == "alimentacao"

    def test_bio_confeitaria(self):
        assert classify_niche(bio="Confeitaria artesanal 🎂 brigadeiros gourmet") == "alimentacao"

    def test_company_pizzaria(self):
        assert classify_niche(company="Pizzaria do Toninho Ltda ME") == "alimentacao"


# ---------------------------------------------------------------------------
# Pet Shop
# ---------------------------------------------------------------------------

class TestPetShop:
    def test_cnpj_veterinaria(self):
        assert classify_niche(atividade="Clínicas e residências veterinárias") == "pet-shop"

    def test_bio_pet(self):
        assert classify_niche(bio="🐾 Petshop e banho e tosa | Campinas SP") == "pet-shop"

    def test_company_petshop(self):
        assert classify_niche(company="Pet Shop da Márcia EIRELI") == "pet-shop"


# ---------------------------------------------------------------------------
# Serviços Jurídicos
# ---------------------------------------------------------------------------

class TestServicosJuridicos:
    def test_cnpj_advocacia(self):
        assert classify_niche(atividade="Atividades jurídicas, exceto cartórios") == "servicos-juridicos"

    def test_bio_advogado(self):
        assert classify_niche(bio="Advogado trabalhista | OAB/SP | consultas online") == "servicos-juridicos"


# ---------------------------------------------------------------------------
# Financeiro
# ---------------------------------------------------------------------------

class TestFinanceiro:
    def test_cnpj_seguros(self):
        assert classify_niche(atividade="Corretores e agentes de seguros, planos de previdência") == "financeiro"

    def test_bio_credito(self):
        assert classify_niche(bio="Correspondente bancário | crédito para MEI e PJ") == "financeiro"

    def test_bio_consorcio(self):
        assert classify_niche(bio="Especialista em consórcio imobiliário e veículos") == "financeiro"


# ---------------------------------------------------------------------------
# Educação
# ---------------------------------------------------------------------------

class TestEducacao:
    def test_cnpj_curso(self):
        assert classify_niche(atividade="Cursos livres e de aperfeiçoamento profissional") == "educacao"

    def test_bio_escola(self):
        assert classify_niche(bio="Escola de inglês para adultos 📚 Matrículas abertas") == "educacao"


# ---------------------------------------------------------------------------
# Imóveis
# ---------------------------------------------------------------------------

class TestImoveis:
    def test_cnpj_imobiliaria(self):
        assert classify_niche(atividade="Atividades imobiliárias por conta própria") == "imoveis"

    def test_bio_corretor(self):
        assert classify_niche(bio="Corretor de imóveis CRECI | compra venda locação") == "imoveis"


# ---------------------------------------------------------------------------
# Tecnologia
# ---------------------------------------------------------------------------

class TestTecnologia:
    def test_cnpj_software(self):
        assert classify_niche(atividade="Desenvolvimento e licenciamento de programas de computador") == "tecnologia"

    def test_bio_startup(self):
        assert classify_niche(bio="Founder de startup SaaS B2B | automação de processos") == "tecnologia"


# ---------------------------------------------------------------------------
# Construção e Reformas
# ---------------------------------------------------------------------------

class TestConstrucaoReformas:
    def test_cnpj_construcao(self):
        assert classify_niche(atividade="Construção de edifícios") == "construcao-reformas"

    def test_bio_reforma(self):
        assert classify_niche(bio="Reforma e decoração de interiores ✂️ | SP e Grande SP") == "construcao-reformas"


# ---------------------------------------------------------------------------
# Contabilidade
# ---------------------------------------------------------------------------

class TestContabilidade:
    def test_cnpj_contabilidade(self):
        assert classify_niche(atividade="Atividades de contabilidade") == "contabilidade"

    def test_company_contador(self):
        assert classify_niche(company="Escritório de Contabilidade Silva & Souza SS Ltda") == "contabilidade"


# ---------------------------------------------------------------------------
# Indústria
# ---------------------------------------------------------------------------

class TestIndustria:
    def test_cnpj_industria(self):
        assert classify_niche(atividade="Fabricação de produtos de borracha e plástico") == "industria"

    def test_cnpj_metalurgica(self):
        assert classify_niche(atividade="Metalurgia de metais não-ferrosos") == "industria"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_all_none_returns_none(self):
        assert classify_niche() is None

    def test_empty_strings_return_none(self):
        assert classify_niche(atividade="", company="", bio="") is None

    def test_ambiguous_bio_returns_highest_score(self):
        # Bio com 2 hits de beleza e 1 hit de fitness → beleza ganha
        result = classify_niche(bio="Manicure e nail designer, também faço depilacao")
        assert result == "beleza-estetica"

    def test_cnpj_weight_beats_bio(self):
        # atividade diz restaurante (×3), bio diz nail (×1) → alimentacao ganha
        result = classify_niche(
            atividade="Restaurante e similares",
            bio="nail e beleza",
        )
        assert result == "alimentacao"

    def test_source_hint_only_when_no_text_match(self):
        # Com texto, source hint não é usado
        result = classify_niche(bio="Clínica médica", source_name="instagram")
        assert result == "saude-bem-estar"

    def test_unknown_source_hint_returns_none(self):
        assert classify_niche(source_name="web_scraping") is None

    def test_google_maps_hint_returns_none(self):
        assert classify_niche(source_name="google_maps") is None
