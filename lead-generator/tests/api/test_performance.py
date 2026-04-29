"""Testes de performance — benchmarks de funções críticas e operações em bulk.

Limites conservadores para ambiente de desenvolvimento.
Todos os testes operam em memória pura — sem banco, sem broker.
"""
import sys
import os
import time
import io
import csv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import MagicMock

import services.api.main as api


# ─── Funções puras ───────────────────────────────────────────────────────────


class TestSlugPerformance:
    def test_1000_chamadas_abaixo_de_500ms(self):
        start = time.monotonic()
        for _ in range(1000):
            api._slug("nail studio de unhas premium em São Paulo SP")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"_slug 1000× levou {elapsed:.3f}s (limite: 0.500s)"

    def test_string_de_1kb_abaixo_de_10ms(self):
        long_text = "nail studio " * 85
        start = time.monotonic()
        api._slug(long_text)
        elapsed = time.monotonic() - start
        assert elapsed < 0.01, f"_slug com ~1KB levou {elapsed:.4f}s (limite: 0.010s)"

    def test_string_so_especiais_abaixo_de_5ms(self):
        """Regex no _slug deve ser eficiente mesmo sem matches."""
        payload = "!@#$%^&*()" * 100
        start = time.monotonic()
        api._slug(payload)
        elapsed = time.monotonic() - start
        assert elapsed < 0.005, f"_slug só especiais levou {elapsed:.4f}s"


class TestEscHtmlPerformance:
    def test_1000_chamadas_abaixo_de_500ms(self):
        payload = "<b>João & Maria</b>" * 10
        start = time.monotonic()
        for _ in range(1000):
            api._esc_html(payload)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"_esc_html 1000× levou {elapsed:.3f}s (limite: 0.500s)"

    def test_string_densa_em_especiais_abaixo_de_100ms(self):
        """Muitos < > & — três replace() encadeados devem ser O(n)."""
        payload = ("<>&" * 333)[:1000]
        start = time.monotonic()
        for _ in range(200):
            api._esc_html(payload)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"_esc_html denso 200× levou {elapsed:.3f}s"

    def test_string_vazia_1000_chamadas_abaixo_de_50ms(self):
        start = time.monotonic()
        for _ in range(1000):
            api._esc_html("")
        elapsed = time.monotonic() - start
        assert elapsed < 0.05, f"_esc_html vazio 1000× levou {elapsed:.3f}s"


class TestFallbackSweepPerformance:
    """_fallback_sweep é chamado para cada lead sem OPENAI_API_KEY.
    Deve processar > 2 leads/ms para não ser gargalo em campanhas grandes.
    """

    def test_1000_leads_abaixo_de_500ms(self):
        lead = MagicMock()
        lead.phone = "+5511999990000"
        lead.instagram_username = None

        score = MagicMock()
        score.score = 75.0
        score.temperature = "HOT"

        start = time.monotonic()
        for _ in range(1000):
            api._fallback_sweep(lead, score)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"_fallback_sweep 1000× levou {elapsed:.3f}s (limite: 0.500s)"

    def test_sem_score_obj_nao_degrada(self):
        """Fallback sem score_obj (None) não deve ser mais lento."""
        lead = MagicMock()
        lead.phone = None
        lead.instagram_username = None

        start = time.monotonic()
        for _ in range(1000):
            api._fallback_sweep(lead, None)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"_fallback_sweep sem score 1000× levou {elapsed:.3f}s"


class TestBuildLeadProfilePerformance:
    def test_1000_chamadas_abaixo_de_1s(self):
        lead = MagicMock()
        lead.name = "Maria Studio Nail Art"
        lead.phone = "+5511999990000"
        lead.metadata_ = {"search_tag": "nail", "address": "Rua X, 123", "rating": 4.9, "reviews": 87}
        lead.instagram_username = "mariastudio"
        lead.instagram_followers = 5000
        lead.instagram_engagement_rate = 4.2
        lead.instagram_account_type = "business"
        lead.instagram_bio = "Studio de unhas premium 💅 Agendamento online"

        score = MagicMock()
        score.score = 82.0
        score.temperature = "HOT"

        start = time.monotonic()
        for _ in range(1000):
            api._build_sweep_lead_profile(lead, score)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"_build_sweep_lead_profile 1000× levou {elapsed:.3f}s"


# ─── CSV parsing ─────────────────────────────────────────────────────────────


class TestCsvParsingPerformance:
    """Simula a lógica do endpoint POST /leads/csv para validar escalabilidade."""

    FIELD_ALIASES = {
        "nome":        ["nome", "name", "razao_social", "empresa_nome"],
        "email":       ["email", "e-mail", "email_contato"],
        "whatsapp":    ["whatsapp", "telefone", "phone", "celular", "fone"],
        "empresa":     ["empresa", "company", "negocio"],
        "localizacao": ["localizacao", "endereco", "address", "cidade"],
    }

    def _get_field(self, row: dict, field: str):
        for alias in self.FIELD_ALIASES.get(field, [field]):
            if alias in row and row[alias].strip():
                return row[alias].strip()
        return None

    def test_resolucao_campos_1000_linhas_abaixo_de_1s(self):
        rows = [
            {"nome": f"Lead {i}", "email": f"lead{i}@test.com", "telefone": "+5511999990000"}
            for i in range(1000)
        ]
        start = time.monotonic()
        for row in rows:
            self._get_field(row, "nome")
            self._get_field(row, "email")
            self._get_field(row, "whatsapp")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Resolução de campos 1000 linhas levou {elapsed:.3f}s"

    def test_parse_csv_1000_linhas_abaixo_de_500ms(self):
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=["nome", "email", "telefone", "localizacao"]
        )
        writer.writeheader()
        for i in range(1000):
            writer.writerow({
                "nome": f"Empresa {i}",
                "email": f"empresa{i}@test.com",
                "telefone": f"+5511{99999 - i:05d}",
                "localizacao": "São Paulo, SP",
            })
        content = output.getvalue().encode("utf-8")

        start = time.monotonic()
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        rows = list(reader)
        elapsed = time.monotonic() - start

        assert len(rows) == 1000
        assert elapsed < 0.5, f"Parse de 1000 linhas CSV levou {elapsed:.3f}s"

    def test_csv_bom_utf8_decodificado_corretamente(self):
        """BOM UTF-8 (gerado pelo Excel) não deve quebrar o parse."""
        header = "﻿nome,email\n"
        row = "Empresa Teste,empresa@test.com\n"
        content = (header + row).encode("utf-8-sig")
        decoded = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded))
        reader.fieldnames = [h.strip().lower() for h in (reader.fieldnames or [])]
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0].get("nome") == "Empresa Teste"

    def test_csv_vazio_retorna_zero_linhas(self):
        content = "nome,email\n"
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 0

    def test_csv_100_linhas_com_alias_variacoes(self):
        """Verifica que o fallback de aliases não degrada com variações de coluna."""
        rows = [
            {"name": f"Lead {i}", "e-mail": f"lead{i}@test.com", "celular": "+5511999990000"}
            for i in range(100)
        ]
        start = time.monotonic()
        for row in rows:
            nome = self._get_field(row, "nome")
            email = self._get_field(row, "email")
            phone = self._get_field(row, "whatsapp")
            assert nome is not None
            assert email is not None
            assert phone is not None
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"Alias lookup 100 linhas levou {elapsed:.3f}s"


# ─── Sweep jobs em escala ────────────────────────────────────────────────────


class TestSweepJobsEscala:
    """GET /progresso e verificação de 409 fazem scan linear no dict sweep_jobs.
    Validar que isso é aceitável com até 200 jobs concorrentes.
    """

    def test_lookup_por_campanha_200_jobs_abaixo_de_500ms(self):
        import services.api.main as mod

        campanha_id = str(uuid4())
        mod.sweep_jobs.clear()

        for i in range(199):
            jid = str(uuid4())
            mod.sweep_jobs[jid] = {
                "job_id": jid,
                "campanha_id": str(uuid4()),
                "status": "completed",
                "started_at": datetime.utcnow().isoformat(),
            }

        jid = str(uuid4())
        mod.sweep_jobs[jid] = {
            "job_id": jid,
            "campanha_id": campanha_id,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
        }

        start = time.monotonic()
        for _ in range(1000):
            matching = [j for j in mod.sweep_jobs.values() if j["campanha_id"] == campanha_id]
        elapsed = time.monotonic() - start

        assert len(matching) == 1
        assert elapsed < 0.5, f"Lookup 1000× com 200 jobs levou {elapsed:.3f}s"
        mod.sweep_jobs.clear()

    def test_verificacao_running_200_jobs_abaixo_de_500ms(self):
        """Verificação de 409 faz scan no dict — deve ser O(n) tolerável."""
        import services.api.main as mod

        campanha_id = str(uuid4())
        mod.sweep_jobs.clear()

        for i in range(200):
            jid = str(uuid4())
            mod.sweep_jobs[jid] = {
                "job_id": jid,
                "campanha_id": str(uuid4()),
                "status": "completed",
            }

        start = time.monotonic()
        for _ in range(1000):
            any(
                j["campanha_id"] == campanha_id and j["status"] == "running"
                for j in mod.sweep_jobs.values()
            )
        elapsed = time.monotonic() - start

        assert elapsed < 0.5, f"Verificação running 1000× com 200 jobs levou {elapsed:.3f}s"
        mod.sweep_jobs.clear()

    def test_feed_append_e_trim_1000_vezes(self):
        """Simula o padrão de append+trim do feed em _run_sweep."""
        job = {"feed": []}
        start = time.monotonic()
        for i in range(1000):
            job["feed"] = ([{"lead_name": f"Lead {i}", "score": 80}] + job["feed"])[:20]
        elapsed = time.monotonic() - start
        assert len(job["feed"]) == 20
        assert elapsed < 0.1, f"Feed append+trim 1000× levou {elapsed:.3f}s"


# ─── Placeholder email ───────────────────────────────────────────────────────


class TestPlaceholderEmailPerformance:
    def test_1000_emails_unicos_abaixo_de_500ms(self):
        start = time.monotonic()
        emails = [api._placeholder_email(f"Lead {i}") for i in range(1000)]
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"_placeholder_email 1000× levou {elapsed:.3f}s"

    def test_unicidade_garantida_entre_1000(self):
        emails = [api._placeholder_email("Maria") for _ in range(1000)]
        assert len(set(emails)) == 1000, "Colisão detectada — unicidade uuid4 violada"
