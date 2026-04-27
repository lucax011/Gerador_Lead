"""Testes unitários das funções utilitárias do CNPJ.ws enricher.

Testa parsing, classificação de porte e extração de CNPJ de metadados.
Não faz chamadas HTTP reais — usa mock para o httpx.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from services.enricher.sources.cnpjws import (
    _extract_cnpj,
    _anos_desde,
    _revenue_tier,
    enrich_from_metadata,
    lookup_cnpj,
)


# ---------------------------------------------------------------------------
# _extract_cnpj
# ---------------------------------------------------------------------------

class TestExtractCnpj:
    def test_cnpj_formatado_com_pontuacao(self):
        assert _extract_cnpj("12.345.678/0001-00") == "12345678000100"

    def test_cnpj_somente_digitos(self):
        assert _extract_cnpj("12345678000100") == "12345678000100"

    def test_cnpj_com_espacos(self):
        assert _extract_cnpj("12 345 678 0001 00") == "12345678000100"

    def test_string_vazia_retorna_none(self):
        assert _extract_cnpj("") is None

    def test_cpf_11_digitos_retorna_none(self):
        """CPF tem 11 dígitos — não é CNPJ."""
        assert _extract_cnpj("123.456.789-00") is None

    def test_string_sem_digitos_retorna_none(self):
        assert _extract_cnpj("sem cnpj aqui") is None

    def test_none_retorna_none(self):
        assert _extract_cnpj(None) is None

    def test_cnpj_15_digitos_retorna_none(self):
        assert _extract_cnpj("123456789012345") is None


# ---------------------------------------------------------------------------
# _anos_desde
# ---------------------------------------------------------------------------

class TestAnosDesdeFuncao:
    def test_data_passada_retorna_anos_corretos(self):
        ano_passado = date.today().year - 5
        resultado = _anos_desde(f"{ano_passado}-01-01")
        assert resultado == 5

    def test_ano_atual_retorna_zero(self):
        ano_atual = date.today().year
        resultado = _anos_desde(f"{ano_atual}-06-15")
        assert resultado == 0

    def test_data_none_retorna_none(self):
        assert _anos_desde(None) is None

    def test_data_invalida_retorna_none(self):
        assert _anos_desde("data-invalida") is None

    def test_data_vazia_retorna_none(self):
        assert _anos_desde("") is None

    def test_empresa_antiga_1990(self):
        resultado = _anos_desde("1990-03-15")
        assert resultado == date.today().year - 1990


# ---------------------------------------------------------------------------
# _revenue_tier
# ---------------------------------------------------------------------------

class TestRevenueTier:
    def test_capital_none_retorna_none(self):
        assert _revenue_tier(None, None) is None

    def test_micro_abaixo_10k(self):
        assert _revenue_tier(5000.0, 2) == "micro"

    def test_micro_exatamente_9999(self):
        assert _revenue_tier(9999.99, 1) == "micro"

    def test_pequeno_entre_10k_e_100k(self):
        assert _revenue_tier(50000.0, 5) == "pequeno"

    def test_pequeno_exatamente_10k(self):
        assert _revenue_tier(10000.0, 3) == "pequeno"

    def test_medio_entre_100k_e_1m(self):
        assert _revenue_tier(500000.0, 10) == "medio"

    def test_grande_acima_1m(self):
        assert _revenue_tier(1_000_000.0, 15) == "grande"

    def test_grande_exatamente_1m(self):
        assert _revenue_tier(1_000_000.0, 20) == "grande"

    def test_zero_retorna_micro(self):
        assert _revenue_tier(0.0, 1) == "micro"


# ---------------------------------------------------------------------------
# lookup_cnpj (mock HTTP)
# ---------------------------------------------------------------------------

class TestLookupCnpj:
    @pytest.mark.asyncio
    async def test_cnpj_valido_retorna_dados(self):
        fake_response = {
            "razao_social": "EMPRESA TESTE LTDA",
            "nome_fantasia": "Empresa Teste",
            "atividade_principal": [{"descricao": "Comércio varejista"}],
            "natureza_juridica": {"descricao": "Sociedade Empresária Limitada"},
            "porte": {"descricao": "ME"},
            "data_inicio_atividade": "2018-05-10",
            "situacao_cadastral": {"descricao": "ATIVA"},
            "logradouro": "Rua das Flores",
            "municipio": "São Paulo",
            "uf": "SP",
            "ddd_telefone_1": "11999990000",
            "email": "contato@empresa.com.br",
            "capital_social": 50000.0,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_response

        with patch("services.enricher.sources.cnpjws.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            result = await lookup_cnpj("12.345.678/0001-00")

        assert result is not None
        assert result["razao_social"] == "EMPRESA TESTE LTDA"
        assert result["situacao"] == "ATIVA"
        assert result["municipio"] == "São Paulo"
        assert result["revenue_tier"] == "pequeno"
        assert result["anos_atividade"] == date.today().year - 2018

    @pytest.mark.asyncio
    async def test_cnpj_invalido_retorna_none(self):
        result = await lookup_cnpj("123")
        assert result is None

    @pytest.mark.asyncio
    async def test_rate_limit_retorna_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch("services.enricher.sources.cnpjws.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            result = await lookup_cnpj("12345678000100")

        assert result is None

    @pytest.mark.asyncio
    async def test_cnpj_nao_encontrado_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("services.enricher.sources.cnpjws.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            result = await lookup_cnpj("12345678000100")

        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_retorna_none(self):
        import httpx
        with patch("services.enricher.sources.cnpjws.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            result = await lookup_cnpj("12345678000100")

        assert result is None


# ---------------------------------------------------------------------------
# enrich_from_metadata
# ---------------------------------------------------------------------------

class TestEnrichFromMetadata:
    @pytest.mark.asyncio
    async def test_cnpj_em_metadata_direto(self):
        fake_result = {"cnpj": "12345678000100", "razao_social": "Teste", "situacao": "ATIVA"}
        with patch("services.enricher.sources.cnpjws.lookup_cnpj", AsyncMock(return_value=fake_result)):
            result = await enrich_from_metadata({"cnpj": "12345678000100"})
        assert result is not None
        assert result["cnpj"] == "12345678000100"

    @pytest.mark.asyncio
    async def test_document_como_fallback(self):
        fake_result = {"cnpj": "12345678000100", "razao_social": "Teste", "situacao": "ATIVA"}
        with patch("services.enricher.sources.cnpjws.lookup_cnpj", AsyncMock(return_value=fake_result)):
            result = await enrich_from_metadata({"document": "12345678000100"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_empresa_cnpj_como_fallback(self):
        fake_result = {"cnpj": "12345678000100", "razao_social": "Teste", "situacao": "ATIVA"}
        with patch("services.enricher.sources.cnpjws.lookup_cnpj", AsyncMock(return_value=fake_result)):
            result = await enrich_from_metadata({"empresa_cnpj": "12.345.678/0001-00"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_metadata_sem_cnpj_retorna_none(self):
        with patch("services.enricher.sources.cnpjws.lookup_cnpj", AsyncMock(return_value=None)):
            result = await enrich_from_metadata({"nome": "sem cnpj"})
        assert result is None

    @pytest.mark.asyncio
    async def test_metadata_vazio_retorna_none(self):
        result = await enrich_from_metadata({})
        assert result is None
