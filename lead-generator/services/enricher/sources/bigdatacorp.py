"""BigDataCorp — stub para enriquecimento pago.

Requer contrato com BigDataCorp (https://bigdatacorp.com.br).
Ativar quando token estiver disponível em BIGDATACORP_TOKEN.

Datasets relevantes:
  - PessoasFisicas: renda estimada, escolaridade, perfil de consumo
  - Empresas: faturamento presumido, porte real, sócios, filiais
  - Financeiro: score de crédito, histórico de inadimplência
  - Contatos: telefones, emails, redes sociais vinculados ao CPF/CNPJ
"""
import structlog

log = structlog.get_logger(__name__)


async def enrich_person(cpf: str, token: str) -> dict:
    """Enriquecimento de pessoa física via BigDataCorp."""
    log.info("BigDataCorp PessoasFisicas — não implementado", cpf=cpf[:3] + "***")
    return {
        "_status": "stub",
        "_message": "BigDataCorp não configurado. Defina BIGDATACORP_TOKEN no .env",
    }


async def enrich_company(cnpj: str, token: str) -> dict:
    """Enriquecimento de empresa via BigDataCorp."""
    log.info("BigDataCorp Empresas — não implementado", cnpj=cnpj[:8] + "***")
    return {
        "_status": "stub",
        "_message": "BigDataCorp não configurado. Defina BIGDATACORP_TOKEN no .env",
    }


# Quando implementar:
# POST https://plataforma.bigdatacorp.com.br/pessoas
# Headers: AccessToken: {token}, TokenId: {token_id}
# Body: { "q": "doc{cpf}", "Datasets": "RendaEstimada,Contatos" }
