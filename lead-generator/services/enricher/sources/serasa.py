"""Serasa Experian — stub para score de crédito.

Prioritário para leads de consórcio (comprador precisa ter crédito).
Requer contrato B2B com Serasa Experian (https://www.serasaexperian.com.br/solucoes/).

API relevante: Serasa Score 3.0 — score 0-1000 de pessoa física.
Endpoint: POST https://api.serasaexperian.com.br/score/v1/scores
Auth: OAuth 2.0 client_credentials (SERASA_CLIENT_ID + SERASA_CLIENT_SECRET)
"""
import structlog

log = structlog.get_logger(__name__)


async def get_credit_score(cpf: str, client_id: str, client_secret: str) -> dict:
    """Score de crédito Serasa para qualificação de consórcio."""
    log.info("Serasa Score — não implementado", cpf=cpf[:3] + "***")
    return {
        "_status": "stub",
        "_message": "Serasa não configurado. Defina SERASA_CLIENT_ID e SERASA_CLIENT_SECRET no .env",
        "_priority": "alta para campanha consórcio",
    }


# Quando implementar:
# 1. POST /oauth/token → access_token
# 2. POST /score/v1/scores { "cpf": "...", "consentimento": "S" }
# 3. Retorna: { "score": 750, "faixa": "BOM", "inadimplente": false }
