"""CNPJ.ws — API pública gratuita para lookup de CNPJ e busca por razão social."""
import re

import httpx
import structlog

log = structlog.get_logger(__name__)

_BASE = "https://publica.cnpj.ws/cnpj"
_HEADERS = {"User-Agent": "LeadGenerator/1.0 (contato@exemplo.com.br)"}


def _extract_cnpj(text: str) -> str | None:
    """Extrai CNPJ de qualquer string (remove pontuação)."""
    digits = re.sub(r"\D", "", text or "")
    if len(digits) == 14:
        return digits
    return None


def _anos_desde(data_str: str | None) -> int | None:
    """Calcula anos desde uma data no formato YYYY-MM-DD."""
    if not data_str:
        return None
    try:
        from datetime import date
        ano = int(data_str[:4])
        return date.today().year - ano
    except Exception:
        return None


def _revenue_tier(capital: float | None, anos: int | None) -> str | None:
    """Classifica porte estimado com base em capital social e tempo."""
    if capital is None:
        return None
    if capital < 10_000:
        return "micro"
    if capital < 100_000:
        return "pequeno"
    if capital < 1_000_000:
        return "medio"
    return "grande"


async def lookup_cnpj(cnpj_raw: str) -> dict | None:
    """
    Faz lookup direto de CNPJ via CNPJ.ws.
    Retorna dict com dados formatados ou None em caso de falha.
    """
    cnpj = _extract_cnpj(cnpj_raw)
    if not cnpj:
        return None

    url = f"{_BASE}/{cnpj}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_HEADERS)
            if resp.status_code == 429:
                log.warning("CNPJ.ws rate limit atingido", cnpj=cnpj)
                return None
            if resp.status_code != 200:
                log.debug("CNPJ não encontrado", cnpj=cnpj, status=resp.status_code)
                return None

            data = resp.json()
            atividade = (data.get("atividade_principal") or [{}])[0]
            abertura = data.get("data_inicio_atividade")
            capital = data.get("capital_social")
            anos = _anos_desde(abertura)

            return {
                "cnpj": cnpj,
                "razao_social": data.get("razao_social"),
                "nome_fantasia": data.get("nome_fantasia") or data.get("razao_social"),
                "atividade_principal": atividade.get("descricao"),
                "natureza_juridica": data.get("natureza_juridica", {}).get("descricao"),
                "porte": data.get("porte", {}).get("descricao"),
                "data_abertura": abertura,
                "situacao": data.get("situacao_cadastral", {}).get("descricao"),
                "logradouro": data.get("logradouro"),
                "municipio": data.get("municipio"),
                "uf": data.get("uf"),
                "telefone": data.get("ddd_telefone_1"),
                "email": data.get("email"),
                "capital_social": capital,
                "anos_atividade": anos,
                "revenue_tier": _revenue_tier(capital, anos),
            }
    except httpx.TimeoutException:
        log.warning("CNPJ.ws timeout", cnpj=cnpj)
        return None
    except Exception as e:
        log.error("CNPJ.ws erro", cnpj=cnpj, error=str(e))
        return None


async def enrich_from_metadata(metadata: dict) -> dict | None:
    """
    Tenta extrair CNPJ de campos de metadados do lead
    (vindos de forms, landing pages, etc.).
    """
    candidates = [
        metadata.get("cnpj"),
        metadata.get("document"),
        metadata.get("empresa_cnpj"),
    ]
    for c in candidates:
        if c:
            result = await lookup_cnpj(str(c))
            if result:
                return result
    return None
