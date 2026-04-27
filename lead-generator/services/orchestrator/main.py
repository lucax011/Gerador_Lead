"""Orchestrator Worker — Cérebro do Motor de Audiência

Consome lead.scored, chama GPT-4o-mini com o perfil completo e decide:
  - Qual oferta se encaixa (nichochat | consorcio | nenhuma)
  - Qual canal de abordagem (whatsapp | instagram_dm | nurture | none)
  - Tom da mensagem (direto | educativo | prova_social | urgencia)
  - Melhor horário de contato
  - Objeções esperadas baseadas no perfil
  - Mensagem de abertura personalizada

Se OPENAI_API_KEY não estiver configurado, passa o lead adiante com decisão padrão
baseada no score (regras determinísticas — não bloqueia o pipeline).
"""
import asyncio
import json
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
from shared.database.models import LeadORM, OrchestrationORM
from shared.database.session import AsyncSessionLocal
from shared.models.events import LeadOrchestratedEvent
from shared.models.lead import Lead, LeadStatus

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

publisher: RabbitMQPublisher

ORCHESTRATION_PROMPT = """Você é o orquestrador de um sistema de prospecção B2B para pequenos negócios brasileiros (nail designers, barbearias, salões de beleza, lash designers e outros profissionais autônomos).

Analise o perfil do lead abaixo e tome as decisões de abordagem. Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem explicações fora do JSON.

Perfil do lead:
{profile}

Produtos disponíveis:
- nichochat: plataforma de CRM + chatbot WhatsApp para gestão de clientes do nicho. Ticket ~R$197/mês. Foco: profissionais com 500+ seguidores, presença no Instagram, WhatsApp ativo com clientes.
- consorcio: consórcio de imóvel ou veículo. Ticket ~R$800/mês. Foco: empresários com CNPJ ativo, renda B+ (R$8k+/mês), buscando crescimento/investimento.

Responda com este JSON exato:
{{
  "offer": "nichochat" | "consorcio" | "ambos" | "nenhuma",
  "approach": "whatsapp" | "instagram_dm" | "nurture" | "none",
  "tone": "direto" | "educativo" | "prova_social" | "urgencia",
  "best_time": "HH:mm–HH:mm",
  "best_time_reason": "motivo em 1 frase",
  "score_adjustment": número entre -10 e +10,
  "objections": ["objeção 1", "objeção 2"],
  "opening_message": "mensagem de abertura personalizada com dado do perfil (máx 3 linhas)",
  "reasoning": "justificativa da decisão em 2-3 frases em português"
}}"""


def _build_profile_text(lead: Lead, score: float, temperature: str, enrichment: dict) -> str:
    ig = enrichment.get("instagram") or {}
    cnpj = enrichment.get("cnpj") or {}

    followers = ig.get("followers") or lead.instagram_followers or 0
    engagement = ig.get("engagement_rate") or lead.instagram_engagement_rate or 0
    account_type = ig.get("account_type") or lead.instagram_account_type or "desconhecido"
    bio = ig.get("bio") or lead.instagram_bio or ""

    lines = [
        f"Nome: {lead.name}",
        f"Email: {lead.email}",
        f"Telefone: {lead.phone or 'não informado'}",
        f"Empresa: {lead.company or 'não informado'}",
        f"Fonte: {lead.source_name}",
        f"Score base: {score:.1f} ({temperature})",
        "",
        "— Instagram —",
        f"Username: @{ig.get('username') or lead.instagram_username or 'não encontrado'}",
        f"Seguidores: {followers:,}",
        f"Engajamento: {engagement:.1f}%",
        f"Tipo de conta: {account_type}",
        f"Bio: {bio[:200] if bio else 'não disponível'}",
        "",
        "— Empresa (CNPJ.ws) —",
        f"CNPJ: {cnpj.get('cnpj', 'não encontrado')}",
        f"Razão social: {cnpj.get('razao_social', 'não disponível')}",
        f"Atividade: {cnpj.get('atividade_principal', 'não disponível')}",
        f"Porte: {cnpj.get('porte', 'não disponível')}",
        f"Tempo de empresa: {cnpj.get('anos_atividade', 'desconhecido')} anos",
        f"Situação: {cnpj.get('situacao', 'desconhecida')}",
        f"Município: {cnpj.get('municipio', '')} {cnpj.get('uf', '')}",
    ]
    return "\n".join(lines)


def _fallback_decision(score: float, temperature: str, lead: Lead) -> dict:
    """Decisão determinística quando OpenAI não está configurado."""
    has_instagram = bool(lead.instagram_username)
    has_phone = bool(lead.phone)
    followers = lead.instagram_followers or 0

    offer = "nenhuma"
    if temperature in ("HOT", "WARM"):
        offer = "nichochat" if has_instagram else "consorcio"

    approach = "none"
    if temperature == "HOT":
        approach = "whatsapp" if has_phone else "instagram_dm"
    elif temperature == "WARM":
        approach = "instagram_dm" if has_instagram else "nurture"

    return {
        "offer": offer,
        "approach": approach,
        "tone": "direto" if temperature == "HOT" else "educativo",
        "best_time": "19h–21h",
        "best_time_reason": "horário padrão para abordagem de profissionais autônomos",
        "score_adjustment": 0.0,
        "objections": ["Preço alto"] if temperature == "WARM" else [],
        "opening_message": f"Oi {lead.name.split()[0]}, vi o seu perfil e achei que poderia te ajudar!",
        "reasoning": "Decisão determinística — OpenAI não configurado. Defina OPENAI_API_KEY para ativar o orquestrador IA.",
        "model_used": "fallback",
    }


async def _call_openai(profile_text: str) -> dict | None:
    try:
        import httpx
        prompt = ORCHESTRATION_PROMPT.format(profile=profile_text)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            decision = json.loads(content)
            decision["prompt_tokens"] = data["usage"]["prompt_tokens"]
            decision["completion_tokens"] = data["usage"]["completion_tokens"]
            decision["model_used"] = settings.openai_model
            return decision
    except Exception as e:
        log.error("OpenAI call failed", error=str(e))
        return None


async def _persist_decision(lead: Lead, decision: dict, final_score: float) -> None:
    async with AsyncSessionLocal() as session:
        orch = OrchestrationORM(
            id=uuid4(),
            lead_id=lead.id,
            offer=decision.get("offer"),
            approach=decision.get("approach"),
            tone=decision.get("tone"),
            best_time=decision.get("best_time"),
            best_time_reason=decision.get("best_time_reason"),
            score_adjustment=decision.get("score_adjustment", 0.0),
            final_score=final_score,
            objections=decision.get("objections", []),
            opening_message=decision.get("opening_message"),
            reasoning=decision.get("reasoning"),
            model_used=decision.get("model_used", settings.openai_model),
            prompt_tokens=decision.get("prompt_tokens", 0),
            completion_tokens=decision.get("completion_tokens", 0),
            decided_at=datetime.utcnow(),
        )
        session.add(orch)
        await session.execute(
            update(LeadORM).where(LeadORM.id == lead.id).values(status=LeadStatus.DISTRIBUTED)
        )
        await session.commit()


async def handle_lead_scored(payload: dict[str, Any]) -> None:
    lead = Lead(**payload["lead"])
    score = payload["score"]
    temperature = payload["temperature"]
    enrichment = payload.get("enrichment", {})

    log.info("Orchestrating lead", lead_id=str(lead.id), score=score, temperature=temperature)

    if not settings.orchestrator_enabled:
        log.info("Orchestrator desativado — passando adiante sem decisão IA")
        decision = _fallback_decision(score, temperature, lead)
    elif settings.openai_api_key:
        profile_text = _build_profile_text(lead, score, temperature, enrichment)
        ai_decision = await _call_openai(profile_text)
        decision = ai_decision or _fallback_decision(score, temperature, lead)
    else:
        log.warning("OPENAI_API_KEY não configurado — usando decisão determinística")
        decision = _fallback_decision(score, temperature, lead)

    adjustment = float(decision.get("score_adjustment") or 0)
    final_score = round(min(max(score + adjustment, 0.0), 100.0), 2)

    await _persist_decision(lead, decision, final_score)

    event = LeadOrchestratedEvent(
        lead=lead,
        score=score,
        temperature=temperature,
        offer=decision.get("offer"),
        approach=decision.get("approach"),
        tone=decision.get("tone"),
        best_time=decision.get("best_time"),
        objections=decision.get("objections", []),
        opening_message=decision.get("opening_message"),
        final_score=final_score,
    )
    await publisher.publish("lead.orchestrated", event.model_dump(mode="json"))
    log.info(
        "Published lead.orchestrated",
        lead_id=str(lead.id),
        offer=decision.get("offer"),
        approach=decision.get("approach"),
        final_score=final_score,
    )


async def main() -> None:
    global publisher
    log.info("Orchestrator worker starting")

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    consumer = RabbitMQConsumer(settings.rabbitmq_url)

    await publisher.connect()
    await consumer.connect()
    log.info("Orchestrator conectado ao RabbitMQ")

    await consumer.consume(
        queue_name="orchestrator.lead.scored",
        routing_key="lead.scored",
        handler=handle_lead_scored,
    )


if __name__ == "__main__":
    asyncio.run(main())
