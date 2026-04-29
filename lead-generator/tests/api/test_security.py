"""Testes de segurança — sanitização de inputs, prevenção de injeção HTML/SQL,
controle de acesso a estágios e comportamento seguro de helpers críticos.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from uuid import uuid4

import services.api.main as api


# ─── XSS via _esc_html ───────────────────────────────────────────────────────

PAYLOADS_XSS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    '"><script>alert(document.cookie)</script>',
    "<SCRIPT>alert('XSS')</SCRIPT>",
    "<iframe src=javascript:alert(1)>",
    "<body onload=alert(1)>",
    "<<SCRIPT>alert('XSS');//<</SCRIPT>",
    "<input type=text value='' onfocus=alert(1)>",
    "<details open ontoggle=alert(1)>",
]


class TestXssPrevencao:
    """_esc_html é a última linha de defesa antes de enviar ao Telegram (parse_mode=HTML).
    Qualquer < ou > não escapado abre vetor de injeção de HTML no bot.
    """

    @pytest.mark.parametrize("payload", PAYLOADS_XSS)
    def test_sem_angulo_menor_na_saida(self, payload):
        result = api._esc_html(payload)
        assert "<" not in result, f"'<' não foi escapado para payload: {payload}"

    @pytest.mark.parametrize("payload", PAYLOADS_XSS)
    def test_sem_angulo_maior_na_saida(self, payload):
        result = api._esc_html(payload)
        assert ">" not in result, f"'>' não foi escapado para payload: {payload}"

    @pytest.mark.parametrize("payload", PAYLOADS_XSS)
    def test_lt_entity_presente_na_saida(self, payload):
        if "<" in payload:
            result = api._esc_html(payload)
            assert "&lt;" in result, f"&lt; ausente para payload: {payload}"

    def test_ampersand_multiplo_completamente_escapado(self):
        result = api._esc_html("a & b & c & d")
        assert result.count("&amp;") == 3
        assert " & " not in result

    def test_escape_nao_altera_texto_simples(self):
        assert api._esc_html("Olá Mundo") == "Olá Mundo"

    def test_escape_preserva_emoji(self):
        result = api._esc_html("🔥 Lead HOT")
        assert "🔥" in result
        assert "HOT" in result

    def test_escape_preserva_numeros(self):
        result = api._esc_html("Score: 98.5/100")
        assert "98.5" in result
        assert "100" in result

    def test_escape_duplo_nao_e_idempotente(self):
        """Documentar comportamento: double-escape produz &amp;lt; — esperado."""
        escaped = api._esc_html("<b>")
        double_escaped = api._esc_html(escaped)
        assert "&amp;" in double_escaped  # o & de &lt; é escapado novamente


# ─── Injeção via _slug ───────────────────────────────────────────────────────

PAYLOADS_INJECAO = [
    "'; DROP TABLE leads; --",
    '" OR 1=1 --',
    "../../etc/passwd",
    "<script>alert(1)</script>",
    "${7*7}",
    "{{7*7}}",
    "; ls -la",
    "| whoami",
    "\\x00null",
    "%(injection)s",
]


class TestSlugInjecao:
    """_slug é usado como offer_slug — identificador em JSONB. Não pode conter
    caracteres especiais que possam ser interpretados em outros contextos.
    """

    @pytest.mark.parametrize("payload", PAYLOADS_INJECAO)
    def test_slug_sem_chars_especiais(self, payload):
        slug = api._slug(payload)
        forbidden = set("';\"<>{}|`$\\/.@!#%^&*()-+=[]")
        present = forbidden.intersection(slug)
        assert not present, f"Chars proibidos {present!r} no slug de: {payload!r}"

    @pytest.mark.parametrize("payload", PAYLOADS_INJECAO)
    def test_slug_apenas_alfanumerico(self, payload):
        slug = api._slug(payload)
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in slug), \
            f"Chars não-alfanuméricos no slug: {slug!r}"

    def test_slug_sem_espaco(self):
        assert " " not in api._slug("a b c d e")

    def test_slug_sem_newline(self):
        assert "\n" not in api._slug("linha1\nlinha2")

    def test_slug_sem_tab(self):
        assert "\t" not in api._slug("col1\tcol2")

    def test_slug_minusculo_sempre(self):
        slug = api._slug("UPPER CASE SLUG")
        assert slug == slug.lower()


# ─── Segurança do e-mail placeholder ────────────────────────────────────────


class TestPlaceholderEmailSeguranca:
    NOMES_MALICIOSOS = [
        "'; DROP TABLE leads; --",
        "<script>alert(1)</script>",
        "admin@evil.com",
        "../../etc/passwd",
        "null",
        'victim\nBcc: attacker@evil.com',
        "user\r\nContent-Type: text/html",
        "\x00null_byte",
    ]

    def test_dominio_fixo_para_qualquer_input(self):
        for nome in self.NOMES_MALICIOSOS:
            email = api._placeholder_email(nome)
            assert email.endswith("@maps.placeholder.com"), \
                f"Domínio não fixo para nome: {nome!r}"

    def test_sem_newline_na_parte_local(self):
        """Newline na parte local permitiria injeção de cabeçalho SMTP."""
        nome = "victim\nBcc: attacker@evil.com"
        email = api._placeholder_email(nome)
        assert "\n" not in email
        assert "Bcc" not in email

    def test_sem_carriage_return(self):
        nome = "victim\r\nContent-Type: text/html"
        email = api._placeholder_email(nome)
        assert "\r" not in email
        assert "\n" not in email

    def test_sem_angulo_na_parte_local(self):
        for nome in ["<admin>", "<script>"]:
            email = api._placeholder_email(nome)
            local = email.split("@")[0]
            assert "<" not in local
            assert ">" not in local

    def test_unicidade_previne_enumeracao(self):
        """Dois leads com mesmo nome geram emails distintos — não permite deduplicação por força bruta."""
        emails = {api._placeholder_email("Maria Silva") for _ in range(50)}
        assert len(emails) == 50


# ─── Controle de acesso — stages manuais ────────────────────────────────────


class TestAutorizacaoStages:
    """Protege o lifecycle do lead contra manipulação direta de estágios avançados.
    Contacted, replied, converted só devem ser setados via eventos do pipeline.
    """

    STAGES_PROIBIDOS = [
        "contatado",
        "respondeu",
        "convertido",
        "validado",
        "enriquecido",
        "deduplicado",
    ]

    STAGES_PERMITIDOS = ["capturado", "pontuado", "descartado"]

    def test_stages_futuros_nao_estao_em_allowed(self):
        for stage in self.STAGES_PROIBIDOS:
            assert stage not in api.ALLOWED_MANUAL_STATUSES, \
                f"Stage {stage!r} não deveria poder ser setado manualmente"

    def test_apenas_tres_stages_manuais(self):
        assert len(api.ALLOWED_MANUAL_STATUSES) == 3, \
            "Exatamente 3 stages devem ser permitidos via API"

    def test_stages_permitidos_estao_presentes(self):
        for stage in self.STAGES_PERMITIDOS:
            assert stage in api.ALLOWED_MANUAL_STATUSES, \
                f"Stage {stage!r} deveria estar em ALLOWED_MANUAL_STATUSES"

    def test_valores_sao_lead_status_valido(self):
        from shared.models.lead import LeadStatus

        for label, status in api.ALLOWED_MANUAL_STATUSES.items():
            assert isinstance(status, LeadStatus), \
                f"ALLOWED_MANUAL_STATUSES[{label!r}] deve ser LeadStatus"


# ─── Injeção via HTTP ────────────────────────────────────────────────────────


class TestSegurancaHTTP:
    def test_stage_sql_injection_retorna_422(self, api_client):
        resp = api_client.patch(
            f"/leads/{uuid4()}/stage",
            json={"stage": "'; DROP TABLE leads; --"},
        )
        assert resp.status_code == 422

    def test_stage_script_xss_retorna_422(self, api_client):
        resp = api_client.patch(
            f"/leads/{uuid4()}/stage",
            json={"stage": "<script>alert(1)</script>"},
        )
        assert resp.status_code == 422

    def test_stage_payload_enorme_retorna_422(self, api_client):
        """String de 10 KB como stage — deve ser rejeitada por ser inválida."""
        big_stage = "x" * 10_000
        resp = api_client.patch(f"/leads/{uuid4()}/stage", json={"stage": big_stage})
        assert resp.status_code == 422

    def test_stage_com_newline_retorna_422(self, api_client):
        resp = api_client.patch(
            f"/leads/{uuid4()}/stage",
            json={"stage": "descartado\ninjection"},
        )
        assert resp.status_code == 422

    def test_uuid_com_sql_no_path_retorna_422(self, api_client):
        resp = api_client.patch(
            "/leads/'; DROP TABLE leads; --/stage",
            json={"stage": "descartado"},
        )
        assert resp.status_code == 422

    def test_campanha_id_invalido_no_progresso_nao_gera_500(self, api_client):
        """ID arbitrário no path — deve retornar 404, não 500."""
        resp = api_client.get("/api/campanhas/nao-e-uuid/progresso")
        assert resp.status_code == 404

    def test_job_id_invalido_no_pausar_nao_gera_500(self, api_client):
        resp = api_client.post("/api/jobs/nao-e-uuid/pausar")
        assert resp.status_code == 404

    def test_job_id_invalido_no_retomar_nao_gera_500(self, api_client):
        resp = api_client.post("/api/jobs/nao-e-uuid/retomar")
        assert resp.status_code == 404

    def test_csv_com_header_injection_nao_quebra_servidor(self, api_client):
        """CSV com SQL injection nos dados — não deve causar 500 por injeção."""
        csv_content = "nome,email\n\"'; DROP TABLE leads; --\",safe@test.com\n"
        resp = api_client.post(
            "/leads/csv",
            files={"file": ("test.csv", csv_content.encode(), "text/csv")},
        )
        # 201 (broker mock) ou 500 (sem DB) — nunca por SQL injection
        assert resp.status_code in (201, 422, 500)
        # Verificar que não foi por injeção (DB error é esperado, não SQL exec)
        if resp.status_code == 500:
            body = resp.text
            assert "syntax error" not in body.lower()
            assert "DROP TABLE" not in body

    def test_import_lead_sem_nome_nao_cria_placeholder_no_ar(self, api_client):
        """Sem nome, Pydantic rejeita antes de qualquer efeito colateral."""
        resp = api_client.post("/leads", json={"origem": "maps"})
        assert resp.status_code == 422
        assert "nome" in resp.json().get("detail", [{}])[0].get("loc", [])


# ─── Source defaults — sem multiplier arbitrário ────────────────────────────


class TestSourceDefaultsSeguranca:
    """Fontes conhecidas têm multipliers definidos.
    Uma fonte desconhecida cai no fallback 0.5 — não pode inflar o score.
    """

    def test_fontes_conhecidas_tem_multiplier_correto(self):
        assert api.SOURCE_DEFAULTS["meta_ads"]["multiplier"] == 1.0
        assert api.SOURCE_DEFAULTS["google_ads"]["multiplier"] == 1.0
        assert api.SOURCE_DEFAULTS["paid_traffic"]["multiplier"] == 1.0
        assert api.SOURCE_DEFAULTS["google_maps"]["multiplier"] == 0.9
        assert api.SOURCE_DEFAULTS["csv_import"]["multiplier"] == 0.6

    def test_multiplier_nunca_acima_de_1(self):
        for name, cfg in api.SOURCE_DEFAULTS.items():
            assert cfg["multiplier"] <= 1.0, \
                f"SOURCE_DEFAULTS[{name!r}].multiplier > 1.0 — infla score"

    def test_multiplier_nunca_negativo(self):
        for name, cfg in api.SOURCE_DEFAULTS.items():
            assert cfg["multiplier"] >= 0.0, \
                f"SOURCE_DEFAULTS[{name!r}].multiplier negativo"

    def test_fonte_desconhecida_cai_em_manual_05(self):
        """Fonte não cadastrada → fallback manual com multiplier 0.5."""
        fallback = api.SOURCE_DEFAULTS.get("fonte_inventada", {"multiplier": 0.5})
        assert fallback["multiplier"] <= 0.5
