"""AI Tagger Worker

Consome lead.enriched, gera tags semânticas e perfil_resumido via GPT-4o-mini,
salva no lead e publica lead.tagged. O sweep usa as tags como pré-filtro
semântico (tags ∩ campanha.keywords_alvo) antes da análise lead × oferta.

Fallback determinístico quando OPENAI_API_KEY ausente.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import update

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.broker.rabbitmq import RabbitMQConsumer, RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import LeadORM
from shared.database.session import AsyncSessionLocal
from shared.models.events import LeadTaggedEvent
from shared.models.lead import Lead, LeadStatus

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher

TAGGING_PROMPT = """\
Você é um classificador de leads B2B. Analise os dados do negócio abaixo e retorne um JSON com:
- "tags": lista de 3 a 8 tags curtas (lowercase, hífens para espaços) que descrevem o negócio.
  Inclua: nicho/tipo de serviço (ex: "nail", "barbearia", "estetica"), tipo jurídico (ex: "MEI"),
  e sinais de qualidade quando presentes (ex: "instagram-ativo", "cnpj-ativo", "alta-seguidores").
- "perfil_resumido": 1-2 frases descrevendo o negócio de forma objetiva.

Responda SOMENTE com JSON válido, sem markdown.

DADOS DO NEGÓCIO:
{profile}
"""


def _build_profile(lead: Lead, enrichment: dict[str, Any]) -> str:
    parts: list[str] = [f"Nome: {lead.name}"]
    if lead.company:
        parts.append(f"Empresa: {lead.company}")
    if lead.phone:
        parts.append(f"Telefone: {lead.phone}")

    search_tag = lead.metadata.get("search_tag", "")
    if search_tag:
        parts.append(f"Nicho buscado: {search_tag}")

    ig = enrichment.get("instagram_data", {})
    if ig.get("username"):
        parts.append(
            f"Instagram: @{ig['username']} | {ig.get('followers', 0)} seguidores | "
            f"engajamento {ig.get('engagement_rate', 0):.1f}% | tipo: {ig.get('account_type', '?')}"
        )
        if ig.get("bio"):
            parts.append(f"Bio Instagram: {str(ig['bio'])[:200]}")

    cnpj = enrichment.get("cnpj_data", {})
    if cnpj.get("cnpj"):
        parts.append(
            f"CNPJ: {cnpj['cnpj']} | {cnpj.get('razao_social', '')} | "
            f"Atividade: {cnpj.get('atividade_principal', '')} | "
            f"Porte: {cnpj.get('porte', '')} | Situação: {cnpj.get('situacao', '')}"
        )

    return "\n".join(parts)


def _fallback_tags(lead: Lead, enrichment: dict[str, Any]) -> tuple[list[str], str]:
    tags: list[str] = []

    search_tag = lead.metadata.get("search_tag", "")
    if search_tag:
        tags.append(search_tag.lower().replace(" ", "-"))

    ig = enrichment.get("instagram_data", {})
    followers = ig.get("followers") or lead.instagram_followers or 0
    if followers >= 10_000:
        tags.extend(["instagram-ativo", "alta-seguidores"])
    elif followers >= 500:
        tags.append("instagram-ativo")

    cnpj = enrichment.get("cnpj_data", {})
    if cnpj.get("situacao", "").upper() in ("ATIVA", "ATIVO"):
        tags.append("cnpj-ativo")
    if cnpj.get("porte", "").upper() == "MICRO EMPRESA":
        tags.append("MEI")

    perfil = f"{lead.name}"
    if lead.company:
        perfil += f" — {lead.company}"
    if search_tag:
        perfil += f". Nicho: {search_tag}."

    return tags, perfil


async def _call_openai(lead: Lead, enrichment: dict[str, Any]) -> tuple[list[str], str] | None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        profile_text = _build_profile(lead, enrichment)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Você é um classificador de leads B2B. Responda SOMENTE com JSON."},
                {"role": "user", "content": TAGGING_PROMPT.format(profile=profile_text)},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        tags = [str(t).lower().strip() for t in data.get("tags", []) if t][:8]
        perfil = str(data.get("perfil_resumido", "")).strip()
        return tags, perfil
    except Exception as exc:
        log.warning("OpenAI tagging failed, using fallback", error=str(exc))
        return None


async def persist_tags(lead_id, tags: list[str], perfil: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(LeadORM)
            .where(LeadORM.id == lead_id)
            .values(
                tags=tags,
                perfil_resumido=perfil,
                status=LeadStatus.TAGGED.value,
            )
        )
        await session.commit()


async def handle_lead_enriched(payload: dict[str, Any]) -> None:
    lead_data = payload["lead"]
    lead = Lead(**lead_data)
    enrichment = payload.get("enrichment", {})
    log.info("Tagging lead", lead_id=str(lead.id), email=lead.email)

    result = await _call_openai(lead, enrichment)
    if result is None:
        tags, perfil = _fallback_tags(lead, enrichment)
        log.info("Used fallback tagging", lead_id=str(lead.id), tags=tags)
    else:
        tags, perfil = result
        log.info("Tagged via OpenAI", lead_id=str(lead.id), tags=tags)

    await persist_tags(lead.id, tags, perfil)

    lead.status = LeadStatus.TAGGED
    lead.tags = tags
    lead.perfil_resumido = perfil

    event = LeadTaggedEvent(lead=lead, tags=tags, perfil_resumido=perfil)
    await publisher.publish("lead.tagged", event.model_dump(mode="json"))
    log.info("Published lead.tagged", lead_id=str(lead.id))


async def main() -> None:
    global publisher
    log.info("AI Tagger worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)

    await publisher.connect()
    await consumer.connect()
    log.info("Connected to RabbitMQ and PostgreSQL")

    await consumer.consume(
        queue_name="tagger.lead.enriched",
        routing_key="lead.enriched",
        handler=handle_lead_enriched,
    )


if __name__ == "__main__":
    asyncio.run(main())
