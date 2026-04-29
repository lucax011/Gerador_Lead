"""Testes unitários das funções auxiliares da API.

Sem banco, sem broker, sem HTTP — cobre lógica pura.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from unittest.mock import MagicMock

import services.api.main as api


# ─── _slug ───────────────────────────────────────────────────────────────────


class TestSlug:
    def test_uppercase_convertido(self):
        assert api._slug("Hello") == "hello"

    def test_espacos_removidos(self):
        assert api._slug("nail studio") == "nailstudio"

    def test_hifen_removido(self):
        assert api._slug("bot-prestador") == "botprestador"

    def test_numeros_mantidos(self):
        assert api._slug("lead123") == "lead123"

    def test_string_vazia(self):
        assert api._slug("") == ""

    def test_pontuacao_removida(self):
        assert api._slug("a!@#$%^&*()b") == "ab"

    def test_apenas_alfanumerico_na_saida(self):
        result = api._slug("Café & Co. Ltda!")
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in result)

    def test_slug_de_nome_comum(self):
        assert api._slug("botprestador") == "botprestador"

    def test_apenas_especiais_resulta_em_vazio(self):
        assert api._slug("!@#$%") == ""


# ─── _placeholder_email ──────────────────────────────────────────────────────


class TestPlaceholderEmail:
    def test_dominio_correto(self):
        email = api._placeholder_email("Maria")
        assert email.endswith("@maps.placeholder.com")

    def test_formato_tem_arroba(self):
        email = api._placeholder_email("João Silva")
        assert "@" in email

    def test_unicidade_entre_100_chamadas(self):
        emails = {api._placeholder_email("Maria") for _ in range(100)}
        assert len(emails) == 100, "Cada chamada deve gerar email único via uuid4"

    def test_parte_local_nao_vazia(self):
        email = api._placeholder_email("Z")
        local = email.split("@")[0]
        assert local, "Parte local não deve ser vazia (hex suffix garante conteúdo)"

    def test_nome_com_especiais_nao_quebra(self):
        email = api._placeholder_email("<script>alert(1)</script>")
        assert email.endswith("@maps.placeholder.com")
        assert "<" not in email
        assert ">" not in email

    def test_nome_vazio_gera_email_valido(self):
        email = api._placeholder_email("")
        assert "@maps.placeholder.com" in email


# ─── _esc_html ───────────────────────────────────────────────────────────────


class TestEscHtml:
    def test_ampersand_escapado(self):
        assert api._esc_html("Tom & Jerry") == "Tom &amp; Jerry"

    def test_menor_escapado(self):
        result = api._esc_html("<b>")
        assert "<" not in result
        assert "&lt;" in result

    def test_maior_escapado(self):
        result = api._esc_html("a > b")
        assert ">" not in result
        assert "&gt;" in result

    def test_script_completamente_escapado(self):
        result = api._esc_html("<script>alert(1)</script>")
        assert "<" not in result
        assert ">" not in result
        assert "&lt;" in result
        assert "&gt;" in result

    def test_sem_mudanca_em_texto_simples(self):
        assert api._esc_html("texto normal") == "texto normal"

    def test_string_vazia(self):
        assert api._esc_html("") == ""

    def test_combinacao_completa(self):
        result = api._esc_html("<b>a & b</b>")
        assert result == "&lt;b&gt;a &amp; b&lt;/b&gt;"

    def test_multiplos_ampersands(self):
        result = api._esc_html("a & b & c")
        assert result.count("&amp;") == 2
        assert " & " not in result

    def test_preserva_texto_unicode(self):
        result = api._esc_html("João 🔥 Silva")
        assert "João" in result
        assert "🔥" in result


# ─── _temperature_emoji ──────────────────────────────────────────────────────


class TestTemperatureEmoji:
    def test_hot(self):
        assert api._temperature_emoji("HOT") == "🔥"

    def test_warm(self):
        assert api._temperature_emoji("WARM") == "🌡️"

    def test_cold(self):
        assert api._temperature_emoji("COLD") == "🧊"

    def test_none_retorna_interrogacao(self):
        assert api._temperature_emoji(None) == "❓"

    def test_desconhecido_retorna_interrogacao(self):
        assert api._temperature_emoji("EXTREME") == "❓"

    def test_minusculo_nao_reconhecido(self):
        assert api._temperature_emoji("hot") == "❓"

    def test_string_vazia_retorna_interrogacao(self):
        assert api._temperature_emoji("") == "❓"


# ─── Mapeamentos ─────────────────────────────────────────────────────────────


class TestOriginToSource:
    def test_maps_vira_google_maps(self):
        assert api.ORIGIN_TO_SOURCE["maps"] == "google_maps"

    def test_instagram_mapeado(self):
        assert api.ORIGIN_TO_SOURCE["instagram"] == "instagram"

    def test_csv_vira_csv_import(self):
        assert api.ORIGIN_TO_SOURCE["csv"] == "csv_import"

    def test_meta_vira_meta_ads(self):
        assert api.ORIGIN_TO_SOURCE["meta"] == "meta_ads"

    def test_google_vira_google_ads(self):
        assert api.ORIGIN_TO_SOURCE["google"] == "google_ads"

    def test_paid_vira_paid_traffic(self):
        assert api.ORIGIN_TO_SOURCE["paid"] == "paid_traffic"

    def test_todos_os_valores_sao_string(self):
        for k, v in api.ORIGIN_TO_SOURCE.items():
            assert isinstance(v, str), f"ORIGIN_TO_SOURCE[{k!r}] deve ser str"

    def test_oito_origens_cadastradas(self):
        assert len(api.ORIGIN_TO_SOURCE) == 8


class TestBackendToPipelineStage:
    def test_captured_vira_capturado(self):
        from shared.models.lead import LeadStatus

        assert api.BACKEND_TO_PIPELINE_STAGE[LeadStatus.CAPTURED.value] == "capturado"

    def test_scored_e_distributed_ambos_pontuado(self):
        from shared.models.lead import LeadStatus

        assert api.BACKEND_TO_PIPELINE_STAGE[LeadStatus.SCORED.value] == "pontuado"
        assert api.BACKEND_TO_PIPELINE_STAGE[LeadStatus.DISTRIBUTED.value] == "pontuado"

    def test_rejected_e_churned_ambos_descartado(self):
        from shared.models.lead import LeadStatus

        assert api.BACKEND_TO_PIPELINE_STAGE[LeadStatus.REJECTED.value] == "descartado"
        assert api.BACKEND_TO_PIPELINE_STAGE[LeadStatus.CHURNED.value] == "descartado"

    def test_validated_mapeado(self):
        from shared.models.lead import LeadStatus

        assert api.BACKEND_TO_PIPELINE_STAGE[LeadStatus.VALIDATED.value] == "validado"


class TestAllowedManualStatuses:
    def test_apenas_tres_permitidos(self):
        assert len(api.ALLOWED_MANUAL_STATUSES) == 3

    def test_descartado_permitido(self):
        assert "descartado" in api.ALLOWED_MANUAL_STATUSES

    def test_capturado_permitido(self):
        assert "capturado" in api.ALLOWED_MANUAL_STATUSES

    def test_pontuado_permitido(self):
        assert "pontuado" in api.ALLOWED_MANUAL_STATUSES

    def test_contatado_nao_permitido(self):
        assert "contatado" not in api.ALLOWED_MANUAL_STATUSES

    def test_respondeu_nao_permitido(self):
        assert "respondeu" not in api.ALLOWED_MANUAL_STATUSES

    def test_convertido_nao_permitido(self):
        assert "convertido" not in api.ALLOWED_MANUAL_STATUSES

    def test_todos_os_valores_sao_lead_status(self):
        from shared.models.lead import LeadStatus

        for v in api.ALLOWED_MANUAL_STATUSES.values():
            assert isinstance(v, LeadStatus)


# ─── _fallback_sweep ─────────────────────────────────────────────────────────


def _lead_mock(phone="+5511999990000", instagram=None):
    lead = MagicMock()
    lead.phone = phone
    lead.instagram_username = instagram
    return lead


def _score_mock(score=75.0, temperature="HOT"):
    s = MagicMock()
    s.score = score
    s.temperature = temperature
    return s


class TestFallbackSweep:
    def test_hot_com_telefone_retorna_whatsapp(self):
        result = api._fallback_sweep(_lead_mock(phone="+5511999990000"), _score_mock(80, "HOT"))
        assert result["channel"] == "whatsapp"

    def test_warm_com_telefone_retorna_whatsapp(self):
        result = api._fallback_sweep(_lead_mock(phone="+5511999990000"), _score_mock(55, "WARM"))
        assert result["channel"] == "whatsapp"

    def test_cold_com_telefone_retorna_nurture(self):
        result = api._fallback_sweep(_lead_mock(phone="+5511999990000"), _score_mock(30, "COLD"))
        assert result["channel"] == "nurture"

    def test_sem_telefone_com_instagram_retorna_instagram_dm(self):
        result = api._fallback_sweep(
            _lead_mock(phone=None, instagram="studio"), _score_mock(80, "HOT")
        )
        assert result["channel"] == "instagram_dm"

    def test_sem_telefone_sem_instagram_retorna_nurture(self):
        result = api._fallback_sweep(
            _lead_mock(phone=None, instagram=None), _score_mock(80, "HOT")
        )
        assert result["channel"] == "nurture"

    def test_score_e_80_porcento_do_original(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock(score=100.0))
        assert result["score"] == 80.0

    def test_score_50_resulta_em_40(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock(score=50.0))
        assert result["score"] == 40.0

    def test_hot_tone_direto(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock(temperature="HOT"))
        assert result["tone"] == "direto"

    def test_warm_tone_educativo(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock(temperature="WARM"))
        assert result["tone"] == "educativo"

    def test_cold_tone_educativo(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock(temperature="COLD"))
        assert result["tone"] == "educativo"

    def test_sem_score_obj_retorna_defaults_seguros(self):
        lead = _lead_mock(phone=None, instagram=None)
        result = api._fallback_sweep(lead, None)
        assert result["channel"] == "nurture"
        assert result["score"] == 0.0
        assert result["insufficient_data"] is True

    def test_score_zero_marca_insufficient_data(self):
        result = api._fallback_sweep(_lead_mock(phone=None), _score_mock(score=0.0, temperature="COLD"))
        assert result["insufficient_data"] is True

    def test_score_positivo_com_contato_nao_e_insufficient(self):
        result = api._fallback_sweep(
            _lead_mock(phone="+5511999990000"), _score_mock(score=60.0, temperature="WARM")
        )
        assert result["insufficient_data"] is False

    def test_sem_nenhum_contato_e_insufficient(self):
        result = api._fallback_sweep(
            _lead_mock(phone=None, instagram=None), _score_mock(score=80.0, temperature="HOT")
        )
        assert result["insufficient_data"] is True

    def test_tem_todas_as_chaves_obrigatorias(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock())
        assert {"score", "channel", "tone", "time", "reason", "insufficient_data"}.issubset(
            result.keys()
        )

    def test_reason_menciona_openai_api_key(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock())
        assert "OPENAI_API_KEY" in result["reason"]

    def test_insufficient_data_e_bool(self):
        result = api._fallback_sweep(_lead_mock(), None)
        assert isinstance(result["insufficient_data"], bool)

    def test_score_resultado_e_float(self):
        result = api._fallback_sweep(_lead_mock(), _score_mock(score=75.0))
        assert isinstance(result["score"], float)


# ─── _build_sweep_lead_profile ───────────────────────────────────────────────


def _lead_orm_mock(**kwargs):
    defaults = dict(
        name="Maria Studio",
        phone="+5511999990000",
        metadata_={},
        instagram_username=None,
        instagram_followers=None,
        instagram_engagement_rate=None,
        instagram_account_type=None,
        instagram_bio=None,
    )
    defaults.update(kwargs)
    lead = MagicMock()
    for k, v in defaults.items():
        setattr(lead, k, v)
    return lead


class TestBuildSweepLeadProfile:
    def test_inclui_nome(self):
        lead = _lead_orm_mock(name="Estúdio Nail")
        profile = api._build_sweep_lead_profile(lead, _score_mock(75.0, "HOT"))
        assert "Estúdio Nail" in profile

    def test_inclui_score(self):
        lead = _lead_orm_mock()
        profile = api._build_sweep_lead_profile(lead, _score_mock(75.0, "HOT"))
        assert "75.0" in profile

    def test_inclui_temperatura(self):
        lead = _lead_orm_mock()
        profile = api._build_sweep_lead_profile(lead, _score_mock(75.0, "HOT"))
        assert "HOT" in profile

    def test_inclui_telefone(self):
        lead = _lead_orm_mock(phone="+5511999990000")
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert "+5511999990000" in profile

    def test_telefone_ausente_exibe_nao_informado(self):
        lead = _lead_orm_mock(phone=None)
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert "não informado" in profile

    def test_inclui_instagram_username(self):
        lead = _lead_orm_mock(instagram_username="studio_nail")
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert "@studio_nail" in profile

    def test_inclui_search_tag_do_metadata(self):
        lead = _lead_orm_mock(metadata_={"search_tag": "nail"})
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert "#nail" in profile

    def test_inclui_avaliacao_google(self):
        lead = _lead_orm_mock(metadata_={"rating": 4.8, "reviews": 123})
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert "4.8" in profile

    def test_trunca_bio_longa_em_200_chars(self):
        lead = _lead_orm_mock(instagram_username="x", instagram_bio="a" * 500)
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert "a" * 200 in profile
        assert "a" * 201 not in profile

    def test_sem_score_exibe_traco(self):
        lead = _lead_orm_mock()
        profile = api._build_sweep_lead_profile(lead, None)
        assert "—" in profile

    def test_retorna_string_nao_vazia(self):
        lead = _lead_orm_mock()
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert isinstance(profile, str)
        assert len(profile) > 0

    def test_sem_instagram_nao_inclui_arroba(self):
        lead = _lead_orm_mock(instagram_username=None)
        profile = api._build_sweep_lead_profile(lead, _score_mock())
        assert "@" not in profile
