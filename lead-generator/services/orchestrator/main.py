"""Orchestrator Worker — Cérebro do Motor de Audiência

Consome lead.scored, chama GPT-4o-mini com o perfil completo e decide:
  - Qual necessidade o empresário tem para vender mais (need_identified)
  - Categoria de oferta ideal (offer_category)
  - Qual canal de abordagem (whatsapp | instagram_dm | nurture | none)
  - Tom da mensagem (direto | educativo | prova_social | urgencia)
  - Melhor horário de contato
  - Objeções esperadas baseadas no perfil
  - Mensagem de abertura personalizada

Produto-agnóstico: a IA decide o que é melhor para cada lead/nicho,
sem restrição a produtos específicos.

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

NICHE_CONTEXTS: dict[str, str] = {
    "ecommerce":          "E-commerce: precisa de mais tráfego e conversão. Foco em automação de carrinho abandonado, retargeting e atendimento rápido via WhatsApp.",
    "beleza-estetica":    "Beleza/Estética: nail designers, salões, barbearias, lash. Alta presença no Instagram, WhatsApp como canal principal. Precisam de agenda cheia e fidelização de clientes recorrentes.",
    "saude-bem-estar":    "Saúde/Bem-estar: clínicas, nutricionistas, psicólogos, academias de yoga. Precisam de pacientes recorrentes e agenda otimizada. Prova social e depoimentos são muito eficazes.",
    "academia-fitness":   "Academia/Fitness: personal trainers, estúdios, boxes de CrossFit. Precisam captar alunos mensalistas e reter matriculados. Sazonalidade: janeiro e pós-Carnaval são picos.",
    "alimentacao":        "Alimentação/Gastronomia: restaurantes, cafés, delivery. Precisam de movimento constante e fidelização. Ticket médio baixo, alto volume. WhatsApp para delivery funciona muito bem.",
    "pet-shop":           "Pet Shop/Veterinária: petshops, clínicas vet, grooming. Dono de pet é cliente fiel quando há confiança. Precisam de agendamento fácil e comunicação proativa.",
    "servicos-juridicos": "Jurídico: advogados, escritórios. Abordagem educativa e de autoridade. Ciclo longo, mas ticket alto. Geração de leads via conteúdo e indicação.",
    "financeiro":         "Financeiro/Fintech: seguros, investimentos, fintechs. Tom profissional e objetivo. Conformidade é objeção comum. CNPJ ativo e renda documentada são qualificadores.",
    "imoveis":            "Imóveis: corretores, imobiliárias, construtoras. Alta comissão tolera alto custo de prospecção. Precisam de leads qualificados de compradores/locatários. WhatsApp é padrão do setor.",
    "educacao":           "Educação: cursos, faculdades, treinamentos. Ciclos de matrícula com picos sazonais. Urgência por vagas + desconto funcionam. Prova social com depoimentos de alunos.",
    "moda-vestuario":     "Moda/Vestuário: boutiques, moda feminina, acessórios. Instagram é canal de vitrine. Precisam de clientes recorrentes e lançamentos. Engajamento alto = boa conversão.",
    "tecnologia":         "Tecnologia/SaaS: empresas de TI, startups. Ciclo de venda longo, múltiplos decisores. Foco em ROI, cases e demos. LinkedIn > Instagram para B2B tech.",
    "construcao-reformas":"Construção/Reformas: construtoras, reformadores, decoradores. Ticket alto, ciclo longo. Indicação e portfólio visual são os principais gatilhos. WhatsApp para orçamentos.",
    "contabilidade":      "Contabilidade/Assessoria: contadores, BPO financeiro. Precisam de MEIs e PMEs como clientes. Dor principal: simplificar obrigações fiscais. Abordagem educativa funciona.",
    "industria":          "Indústria/B2B: manufatura, automação, fornecedores. Ciclo longo, decisão em comitê. Confiança e relacionamento acima de tudo. Feiras e LinkedIn são canais naturais.",
}

ORCHESTRATION_PROMPT = """Você é um orquestrador de prospecção B2B que analisa perfis de donos de pequenas e médias empresas brasileiras e decide a melhor forma de abordagem comercial.

OBJETIVO: Identificar empresários que querem VENDER MAIS e recomendar a melhor solução e abordagem para eles. Você não está preso a produtos específicos — avalie o que faz mais sentido para o perfil do lead (automação de atendimento, captação de clientes, crédito para expansão, presença digital, gestão de agenda, fidelização, etc.).

Analise o perfil abaixo e responda EXCLUSIVAMENTE em JSON válido, sem markdown.

Perfil do lead:
{profile}

Contexto do nicho:
{niche_context}

Responda com este JSON exato:
{{
  "need_identified": "necessidade principal identificada em 1 frase (ex: 'captação de novos clientes via Instagram', 'automação do atendimento WhatsApp', 'crédito para abrir segunda unidade')",
  "offer_category": "crm_atendimento | captacao_clientes | credito_expansao | marketing_digital | gestao_agenda | fidelizacao | outro",
  "approach": "whatsapp" | "instagram_dm" | "nurture" | "none",
  "tone": "direto" | "educativo" | "prova_social" | "urgencia",
  "best_time": "HH:mm–HH:mm",
  "best_time_reason": "motivo em 1 frase",
  "score_adjustment": número entre -10 e +10,
  "objections": ["objeção 1", "objeção 2"],
  "opening_message": "mensagem de abertura personalizada com dado real do perfil, máx 3 linhas, sem pitch genérico",
  "reasoning": "justificativa da decisão em 2-3 frases em português"
}}"""


def _build_profile_text(lead: Lead, score: float, temperature: str, enrichment: dict, niche_name: str | None = None) -> tuple[str, str]:
    """Returns (profile_text, niche_context)."""
    ig = enrichment.get("instagram") or {}
    cnpj = enrichment.get("cnpj") or {}

    followers = ig.get("followers") or lead.instagram_followers or 0
    engagement = ig.get("engagement_rate") or lead.instagram_engagement_rate or 0
    account_type = ig.get("account_type") or lead.instagram_account_type or "desconhecido"
    bio = ig.get("bio") or lead.instagram_bio or ""

    niche_slug = enrichment.get("niche_slug") or ""
    niche_context = NICHE_CONTEXTS.get(niche_slug, "Nicho não mapeado — avalie o perfil e decida com base nos dados disponíveis.")

    lines = [
        f"Nome: {lead.name}",
        f"Email: {lead.email}",
        f"Telefone: {lead.phone or 'não informado'}",
        f"Empresa: {lead.company or 'não informado'}",
        f"Nicho: {niche_name or 'não classificado'}",
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
    return "\n".join(lines), niche_context


def _fallback_decision(score: float, temperature: str, lead: Lead) -> dict:
    """Decisão determinística quando OpenAI não está configurado."""
    has_instagram = bool(lead.instagram_username)
    has_phone = bool(lead.phone)
    followers = lead.instagram_followers or 0

    if temperature == "COLD":
        need = "reengajamento futuro"
        offer_category = "outro"
    elif has_instagram and followers >= 500:
        need = "captação de clientes via Instagram e automação de atendimento"
        offer_category = "crm_atendimento"
    elif has_phone:
        need = "captação de novos clientes via abordagem direta"
        offer_category = "captacao_clientes"
    else:
        need = "presença digital e captação de leads qualificados"
        offer_category = "marketing_digital"

    approach = "none"
    if temperature == "HOT":
        approach = "whatsapp" if has_phone else "instagram_dm"
    elif temperature == "WARM":
        approach = "instagram_dm" if has_instagram else "nurture"

    first_name = lead.name.split()[0]
    return {
        "need_identified": need,
        "offer_category": offer_category,
        "approach": approach,
        "tone": "direto" if temperature == "HOT" else "educativo",
        "best_time": "19h–21h",
        "best_time_reason": "horário padrão para abordagem de profissionais autônomos",
        "score_adjustment": 0.0,
        "objections": ["Preço alto"] if temperature == "WARM" else [],
        "opening_message": f"Oi {first_name}, vi o seu perfil e queria entender melhor como você está captando clientes hoje.",
        "reasoning": "Decisão determinística — OpenAI não configurado. Defina OPENAI_API_KEY para ativar o orquestrador IA.",
        "model_used": "fallback",
    }


async def _call_openai(profile_text: str, niche_context: str) -> dict | None:
    try:
        import httpx
        prompt = ORCHESTRATION_PROMPT.format(profile=profile_text, niche_context=niche_context)
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
            need_identified=decision.get("need_identified"),
            offer=decision.get("offer_category") or decision.get("offer"),
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
    niche_name = payload.get("niche_name")

    log.info("Orchestrating lead", lead_id=str(lead.id), score=score, temperature=temperature)

    if not settings.orchestrator_enabled:
        log.info("Orchestrator desativado — passando adiante sem decisão IA")
        decision = _fallback_decision(score, temperature, lead)
    elif settings.openai_api_key:
        profile_text, niche_context = _build_profile_text(lead, score, temperature, enrichment, niche_name)
        ai_decision = await _call_openai(profile_text, niche_context)
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
        offer=decision.get("offer_category") or decision.get("offer"),
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
