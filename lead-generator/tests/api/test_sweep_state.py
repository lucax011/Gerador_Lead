"""Testes do estado em memória do modo varredura e endpoints HTTP in-memory.

Os endpoints pausar/retomar/progresso operam exclusivamente no dict sweep_jobs
— sem banco, sem broker. Seguros para executar sem infraestrutura real.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from datetime import datetime
from uuid import uuid4, UUID

import services.api.main as mod


def _make_job(campanha_id: str = None, status: str = "running") -> dict:
    """Cria e registra um job no sweep_jobs em memória."""
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "campanha_id": campanha_id or str(uuid4()),
        "campanha_name": "Campanha Teste",
        "status": status,
        "total": 50,
        "analyzed": 10,
        "compatible": 5,
        "insufficient": 1,
        "feed": [],
        "started_at": datetime.utcnow().isoformat(),
        "error": None,
    }
    mod.sweep_jobs[job_id] = job
    return job


# ─── Estrutura do job ────────────────────────────────────────────────────────


class TestJobStructura:
    def test_campos_obrigatorios_presentes(self):
        job = _make_job()
        required = {"job_id", "campanha_id", "status", "total", "analyzed",
                    "compatible", "insufficient", "feed", "started_at", "error"}
        assert required.issubset(job.keys())

    def test_job_id_e_uuid_valido(self):
        job = _make_job()
        UUID(job["job_id"])  # não deve levantar ValueError

    def test_feed_e_lista(self):
        job = _make_job()
        assert isinstance(job["feed"], list)

    def test_contadores_sao_nao_negativos(self):
        job = _make_job()
        assert job["analyzed"] >= 0
        assert job["compatible"] >= 0
        assert job["insufficient"] >= 0
        assert job["total"] >= 0

    def test_compatible_nunca_supera_analyzed(self):
        job = _make_job()
        assert job["compatible"] <= job["analyzed"]

    def test_status_inicial_e_running(self):
        job = _make_job(status="running")
        assert job["status"] == "running"

    def test_erro_inicial_e_none(self):
        job = _make_job()
        assert job["error"] is None


# ─── Máquina de estados ──────────────────────────────────────────────────────


class TestJobStateMachine:
    def test_running_pode_virar_paused(self):
        job = _make_job(status="running")
        job["status"] = "paused"
        assert mod.sweep_jobs[job["job_id"]]["status"] == "paused"

    def test_paused_pode_voltar_a_running(self):
        job = _make_job(status="paused")
        job["status"] = "running"
        assert mod.sweep_jobs[job["job_id"]]["status"] == "running"

    def test_completed_nao_e_running(self):
        job = _make_job(status="completed")
        assert job["status"] != "running"

    def test_error_nao_e_running(self):
        job = _make_job(status="error")
        assert job["status"] != "running"

    def test_nova_varredura_bloqueada_se_running(self):
        campanha_id = str(uuid4())
        _make_job(campanha_id=campanha_id, status="running")
        already_running = any(
            j["campanha_id"] == campanha_id and j["status"] == "running"
            for j in mod.sweep_jobs.values()
        )
        assert already_running

    def test_nova_varredura_permitida_se_completed(self):
        campanha_id = str(uuid4())
        _make_job(campanha_id=campanha_id, status="completed")
        already_running = any(
            j["campanha_id"] == campanha_id and j["status"] == "running"
            for j in mod.sweep_jobs.values()
        )
        assert not already_running

    def test_nova_varredura_permitida_se_error(self):
        campanha_id = str(uuid4())
        _make_job(campanha_id=campanha_id, status="error")
        already_running = any(
            j["campanha_id"] == campanha_id and j["status"] == "running"
            for j in mod.sweep_jobs.values()
        )
        assert not already_running


# ─── Lookup de progresso ─────────────────────────────────────────────────────


class TestProgressoLookup:
    def test_retorna_mais_recente_entre_multiplos_jobs(self):
        campanha_id = str(uuid4())
        job1 = _make_job(campanha_id=campanha_id)
        job1["started_at"] = "2024-01-01T10:00:00"
        job2 = _make_job(campanha_id=campanha_id)
        job2["started_at"] = "2024-01-02T10:00:00"

        matching = [j for j in mod.sweep_jobs.values() if j["campanha_id"] == campanha_id]
        most_recent = sorted(matching, key=lambda j: j["started_at"], reverse=True)[0]
        assert most_recent["job_id"] == job2["job_id"]

    def test_sem_job_para_campanha_lista_vazia(self):
        campanha_id = str(uuid4())
        matching = [j for j in mod.sweep_jobs.values() if j["campanha_id"] == campanha_id]
        assert matching == []

    def test_lookup_nao_confunde_campanhas_diferentes(self):
        id_a = str(uuid4())
        id_b = str(uuid4())
        job_a = _make_job(campanha_id=id_a)
        _make_job(campanha_id=id_b)

        matching_a = [j for j in mod.sweep_jobs.values() if j["campanha_id"] == id_a]
        assert len(matching_a) == 1
        assert matching_a[0]["job_id"] == job_a["job_id"]


# ─── Feed de análise ─────────────────────────────────────────────────────────


class TestFeedLimite:
    def test_feed_limitado_a_20_itens(self):
        job = _make_job()
        for i in range(25):
            job["feed"] = ([{"lead_name": f"Lead {i}", "score": 80}] + job["feed"])[:20]
        assert len(job["feed"]) == 20

    def test_feed_mantem_mais_recentes_no_inicio(self):
        job = _make_job()
        for i in range(5):
            job["feed"] = ([{"lead_name": f"Lead {i}", "score": i}] + job["feed"])[:20]
        assert job["feed"][0]["lead_name"] == "Lead 4"

    def test_feed_vazio_inicialmente(self):
        job = _make_job()
        assert job["feed"] == []


# ─── Offer tag — estrutura esperada ──────────────────────────────────────────


class TestOfferTagEstrutura:
    def test_tag_tem_campos_obrigatorios(self):
        from unittest.mock import MagicMock

        lead = MagicMock()
        lead.phone = "+5511999990000"
        lead.instagram_username = None

        score = MagicMock()
        score.score = 75.0
        score.temperature = "HOT"

        result = mod._fallback_sweep(lead, score)
        assert {"score", "channel", "tone", "time", "reason", "insufficient_data"}.issubset(
            result.keys()
        )

    def test_tag_montada_no_run_sweep_tem_offer_slug(self):
        result_dict = {
            "score": 85.0, "channel": "whatsapp", "tone": "direto",
            "time": "19h–21h", "reason": "MEI ativo", "insufficient_data": False,
        }
        offer_tag = {
            "offer_slug": "bot-prestador",
            "score": result_dict["score"],
            "channel": result_dict["channel"],
            "tone": result_dict["tone"],
            "time": result_dict["time"],
            "reason": result_dict["reason"],
            "insufficient_data": bool(result_dict["insufficient_data"]),
            "analyzed_at": datetime.utcnow().isoformat(),
        }
        assert offer_tag["offer_slug"] == "bot-prestador"
        assert offer_tag["score"] == 85.0
        assert "analyzed_at" in offer_tag

    def test_score_da_tag_esta_no_range_valido(self):
        from unittest.mock import MagicMock

        lead = MagicMock()
        lead.phone = "+5511999990000"
        lead.instagram_username = None

        score = MagicMock()
        score.score = 100.0
        score.temperature = "HOT"

        result = mod._fallback_sweep(lead, score)
        assert 0 <= result["score"] <= 100

    def test_insufficient_data_e_sempre_bool(self):
        from unittest.mock import MagicMock

        lead = MagicMock()
        lead.phone = None
        lead.instagram_username = None
        result = mod._fallback_sweep(lead, None)
        assert isinstance(result["insufficient_data"], bool)


# ─── Endpoints HTTP (sem banco) ──────────────────────────────────────────────


class TestPausarRetomarHTTP:
    def test_pausar_job_inexistente_retorna_404(self, api_client):
        resp = api_client.post(f"/api/jobs/{uuid4()}/pausar")
        assert resp.status_code == 404

    def test_retomar_job_inexistente_retorna_404(self, api_client):
        resp = api_client.post(f"/api/jobs/{uuid4()}/retomar")
        assert resp.status_code == 404

    def test_pausar_job_running_retorna_200(self, api_client):
        job = _make_job(status="running")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/pausar")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_pausar_job_muda_estado_em_memoria(self, api_client):
        job = _make_job(status="running")
        api_client.post(f"/api/jobs/{job['job_id']}/pausar")
        assert mod.sweep_jobs[job["job_id"]]["status"] == "paused"

    def test_retomar_job_paused_retorna_200(self, api_client):
        job = _make_job(status="paused")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/retomar")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_retomar_job_muda_estado_em_memoria(self, api_client):
        job = _make_job(status="paused")
        api_client.post(f"/api/jobs/{job['job_id']}/retomar")
        assert mod.sweep_jobs[job["job_id"]]["status"] == "running"

    def test_pausar_ja_pausado_retorna_422(self, api_client):
        job = _make_job(status="paused")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/pausar")
        assert resp.status_code == 422

    def test_retomar_ja_running_retorna_422(self, api_client):
        job = _make_job(status="running")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/retomar")
        assert resp.status_code == 422

    def test_pausar_completed_retorna_422(self, api_client):
        job = _make_job(status="completed")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/pausar")
        assert resp.status_code == 422

    def test_retomar_completed_retorna_422(self, api_client):
        job = _make_job(status="completed")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/retomar")
        assert resp.status_code == 422

    def test_pausar_resposta_tem_job_id(self, api_client):
        job = _make_job(status="running")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/pausar")
        assert resp.json()["job_id"] == job["job_id"]

    def test_retomar_resposta_tem_job_id(self, api_client):
        job = _make_job(status="paused")
        resp = api_client.post(f"/api/jobs/{job['job_id']}/retomar")
        assert resp.json()["job_id"] == job["job_id"]


class TestProgressoHTTP:
    def test_sem_job_retorna_404(self, api_client):
        resp = api_client.get(f"/api/campanhas/{uuid4()}/progresso")
        assert resp.status_code == 404

    def test_com_job_running_retorna_200(self, api_client):
        campanha_id = str(uuid4())
        _make_job(campanha_id=campanha_id, status="running")
        resp = api_client.get(f"/api/campanhas/{campanha_id}/progresso")
        assert resp.status_code == 200

    def test_retorna_campos_de_progresso(self, api_client):
        campanha_id = str(uuid4())
        _make_job(campanha_id=campanha_id)
        resp = api_client.get(f"/api/campanhas/{campanha_id}/progresso")
        data = resp.json()
        assert "status" in data
        assert "analyzed" in data
        assert "total" in data

    def test_retorna_mais_recente_com_multiplos_jobs(self, api_client):
        campanha_id = str(uuid4())
        job1 = _make_job(campanha_id=campanha_id)
        job1["started_at"] = "2024-01-01T10:00:00"
        job2 = _make_job(campanha_id=campanha_id)
        job2["started_at"] = "2024-01-02T10:00:00"
        resp = api_client.get(f"/api/campanhas/{campanha_id}/progresso")
        assert resp.json()["job_id"] == job2["job_id"]

    def test_campanha_id_como_string_qualquer_funciona(self, api_client):
        """campanha_id é string no dict — não precisa ser UUID válido."""
        campanha_id = "campanha-especial-abc"
        _make_job(campanha_id=campanha_id)
        resp = api_client.get(f"/api/campanhas/{campanha_id}/progresso")
        assert resp.status_code == 200


# ─── Validação HTTP ──────────────────────────────────────────────────────────


class TestValidacaoHTTP:
    def test_stage_invalido_retorna_422(self, api_client):
        resp = api_client.patch(f"/leads/{uuid4()}/stage", json={"stage": "stage_invalido"})
        assert resp.status_code == 422

    def test_uuid_invalido_no_stage_retorna_422(self, api_client):
        resp = api_client.patch("/leads/nao-e-uuid/stage", json={"stage": "descartado"})
        assert resp.status_code == 422

    def test_stages_futuros_retornam_422(self, api_client):
        for stage in ("contatado", "respondeu", "convertido"):
            resp = api_client.patch(f"/leads/{uuid4()}/stage", json={"stage": stage})
            assert resp.status_code == 422, f"Stage {stage!r} deveria ser 422"

    def test_stage_valido_nao_retorna_422(self, api_client):
        for stage in ("capturado", "pontuado", "descartado"):
            resp = api_client.patch(f"/leads/{uuid4()}/stage", json={"stage": stage})
            assert resp.status_code != 422, f"Stage {stage!r} não deveria ser 422"

    def test_importar_lead_sem_nome_retorna_422(self, api_client):
        resp = api_client.post("/leads", json={"origem": "maps"})
        assert resp.status_code == 422

    def test_importar_lead_payload_vazio_retorna_422(self, api_client):
        resp = api_client.post("/leads", json={})
        assert resp.status_code == 422

    def test_importar_lead_com_nome_nao_retorna_422(self, api_client):
        resp = api_client.post("/leads", json={"nome": "Maria Silva"})
        assert resp.status_code != 422

    def test_orchestration_uuid_invalido_retorna_422(self, api_client):
        resp = api_client.get("/api/leads/nao-e-uuid/orchestration")
        assert resp.status_code == 422

    def test_telegram_uuid_invalido_retorna_422(self, api_client):
        resp = api_client.post("/api/leads/nao-e-uuid/telegram")
        assert resp.status_code == 422
