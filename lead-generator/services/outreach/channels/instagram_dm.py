"""Instagram DM — stub para abordagem via Direct Message.

Zona cinzenta: a API oficial do Instagram não permite DM automatizado para contas
que não sejam Pages verificadas com permissão `instagram_manage_messages`.

Alternativas avaliadas:
1. Instagram Graph API (oficial) — requer aprovação Meta, apenas para Pages, não para
   contas pessoais/criadores. Aprovação leva semanas e tem restrições severas.
2. Automação via browser (Puppeteer/Playwright) — viola Termos de Uso do Instagram,
   risco de ban permanente da conta. NÃO recomendado para produção.
3. Manual assistida — dashboard mostra a mensagem gerada pelo orquestrador e o
   operador envia manualmente. Mais seguro para MVP.

DECISÃO MVP: Instagram DM fica como stub. O orquestrador pode recomendar
approach="instagram_dm" mas o Outreach só executa whatsapp por ora.
A mensagem gerada fica salva em outreach_attempts para envio manual via dashboard.
"""
import structlog

log = structlog.get_logger(__name__)


async def send_dm(username: str, message: str) -> dict:
    """Stub — DM Instagram não automatizado no MVP."""
    log.info(
        "Instagram DM — envio manual requerido",
        username=username,
        message_preview=message[:60] + "...",
    )
    return {
        "success": False,
        "manual_required": True,
        "username": username,
        "message": message,
        "reason": "Instagram DM automatizado não disponível no MVP. Enviar manualmente pelo app.",
    }
