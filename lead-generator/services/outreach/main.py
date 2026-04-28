"""Outreach Worker — Executa o contato definido pelo Orquestrador IA.

Consome lead.orchestrated e envia a mensagem no canal correto:
  - whatsapp → Evolution API (ativo quando EVOLUTION_API_URL configurado)
  - instagram_dm → stub (manual no MVP)
  - nurture → agendado para follow-up futuro (stub)
  - none → registra sem enviar

Salva OutreachAttemptORM para rastreamento e dashboard.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4
from datetime import datetime

import structlog
from sqlalchemy import update

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQConsumer, RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import LeadORM, OutreachAttemptORM
from shared.database.session import AsyncSessionLocal
from shared.models.lead import Lead, LeadStatus
from services.outreach.channels.whatsapp import WhatsAppChannel
from services.outreach.channels.instagram_dm import send_dm

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher
_whatsapp: WhatsAppChannel | None = None


def _get_whatsapp() -> WhatsAppChannel | None:
    global _whatsapp
    if _whatsapp is None and settings.evolution_api_url and settings.evolution_api_key:
        _whatsapp = WhatsAppChannel(
            api_url=settings.evolution_api_url,
            api_key=settings.evolution_api_key,
            instance=settings.evolution_instance,
        )
    return _whatsapp


async def _persist_attempt(
    lead: Lead,
    channel: str,
    status: str,
    message: str | None,
    external_id: str | None = None,
    error: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        attempt = OutreachAttemptORM(
            id=uuid4(),
            lead_id=lead.id,
            channel=channel,
            status=status,
            message_text=message,
            external_id=external_id,
            sent_at=datetime.utcnow() if status == "sent" else None,
            error=error,
            attempt_number=1,
            created_at=datetime.utcnow(),
        )
        session.add(attempt)
        if status == "sent":
            await session.execute(
                update(LeadORM).where(LeadORM.id == lead.id).values(status=LeadStatus.CONTACTED)
            )
        await session.commit()


async def handle_lead_orchestrated(payload: dict[str, Any]) -> None:
    lead = Lead(**payload["lead"])
    approach = payload.get("approach") or "none"
    opening_message = payload.get("opening_message")
    offer = payload.get("offer")
    final_score = payload.get("final_score") or payload.get("score")

    log.info(
        "Processing outreach",
        lead_id=str(lead.id),
        approach=approach,
        offer=offer,
        final_score=final_score,
    )

    if not settings.outreach_enabled:
        log.info("Outreach desativado — registrando sem enviar. Defina OUTREACH_ENABLED=true no .env")
        await _persist_attempt(lead, approach, "skipped", opening_message,
                               error="OUTREACH_ENABLED=false")
        return

    if approach == "whatsapp":
        if not lead.phone:
            log.warning("Lead sem telefone — não pode enviar WhatsApp", lead_id=str(lead.id))
            await _persist_attempt(lead, "whatsapp", "failed", opening_message,
                                   error="Lead sem número de telefone")
            return

        wa = _get_whatsapp()
        if not wa:
            log.warning("Evolution API não configurada — registrando para envio manual")
            await _persist_attempt(lead, "whatsapp", "pending_manual", opening_message,
                                   error="EVOLUTION_API_URL ou EVOLUTION_API_KEY não configurados")
            return

        message = opening_message or f"Oi {lead.name.split()[0]}! Vi o seu perfil e tenho algo que pode te ajudar 🚀"
        result = await wa.send_text(lead.phone, message)

        if result["success"]:
            await _persist_attempt(lead, "whatsapp", "sent", message, external_id=result.get("external_id"))
            log.info("WhatsApp enviado com sucesso", lead_id=str(lead.id))
        else:
            await _persist_attempt(lead, "whatsapp", "failed", message, error=result.get("error"))
            log.error("Falha ao enviar WhatsApp", lead_id=str(lead.id), error=result.get("error"))

    elif approach == "instagram_dm":
        username = lead.instagram_username
        if not username:
            log.warning("Lead sem Instagram username", lead_id=str(lead.id))
            await _persist_attempt(lead, "instagram_dm", "failed", opening_message,
                                   error="Lead sem instagram_username")
            return

        message = opening_message or f"Oi @{username}! Vi o seu perfil e tenho algo que pode te ajudar 🚀"
        result = await send_dm(username, message)
        # DM é stub → sempre registra como pending_manual
        await _persist_attempt(lead, "instagram_dm", "pending_manual", message,
                               error=result.get("reason"))
        log.info("Instagram DM registrado para envio manual", lead_id=str(lead.id), username=username)

    elif approach == "nurture":
        log.info("Lead em nurture — sem contato imediato", lead_id=str(lead.id))
        await _persist_attempt(lead, "nurture", "scheduled", opening_message)

    else:
        log.info("Approach 'none' — lead não será abordado agora", lead_id=str(lead.id))
        await _persist_attempt(lead, "none", "skipped", None)


async def main() -> None:
    global publisher
    log.info("Outreach worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)

    await publisher.connect()
    await consumer.connect()
    log.info("Outreach conectado ao RabbitMQ")

    await consumer.consume(
        queue_name="outreach.lead.orchestrated",
        routing_key="lead.orchestrated",
        handler=handle_lead_orchestrated,
    )


if __name__ == "__main__":
    asyncio.run(main())
