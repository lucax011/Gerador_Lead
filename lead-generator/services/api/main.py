import asyncio
import csv
import io
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

import httpx
import structlog
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from shared.broker.rabbitmq import RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import CampaignORM, LeadORM, OrchestrationORM, ScoreORM, SourceORM
from shared.models.events import LeadCapturedEvent
from shared.models.lead import Lead, LeadStatus

logger = structlog.get_logger(__name__)
settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

publisher: RabbitMQPublisher | None = None

# ── Status mappings ────────────────────────────────────────────────────────────

# Maps origin string from frontend to source name in DB
ORIGIN_TO_SOURCE: dict[str, str] = {
    "maps":      "google_maps",
    "instagram": "instagram",
    "csv":       "csv_import",
    "whatsapp":  "whatsapp",
    "meta":      "meta_ads",
    "google":    "google_ads",
    "paid":      "paid_traffic",
    "manual":    "manual",
}

# Pipeline stages shown in the frontend (captured statuses only — future stages excluded)
BACKEND_TO_PIPELINE_STAGE: dict[str, str] = {
    LeadStatus.CAPTURED.value:     "capturado",
    LeadStatus.VALIDATED.value:    "validado",
    LeadStatus.DEDUPLICATED.value: "deduplicado",
    LeadStatus.ENRICHED.value:     "enriquecido",
    LeadStatus.SCORED.value:       "pontuado",
    LeadStatus.DISTRIBUTED.value:  "pontuado",
    LeadStatus.REJECTED.value:     "descartado",
    # Future stages — kept for mapping completeness, hidden in UI
    LeadStatus.CONTACTED.value:    "contatado",
    LeadStatus.REPLIED.value:      "respondeu",
    LeadStatus.CONVERTED.value:    "convertido",
    LeadStatus.CHURNED.value:      "descartado",
}

# Manual status overrides allowed from the frontend (future stages excluded)
ALLOWED_MANUAL_STATUSES: dict[str, LeadStatus] = {
    "capturado":  LeadStatus.CAPTURED,
    "pontuado":   LeadStatus.SCORED,
    "descartado": LeadStatus.CHURNED,
}

# Source defaults for auto-seeding
SOURCE_DEFAULTS: dict[str, dict] = {
    "google_maps":  {"label": "Google Maps",       "channel": "manual",  "multiplier": 0.9},
    "csv_import":   {"label": "Importação CSV",     "channel": "manual",  "multiplier": 0.6},
    "instagram":    {"label": "Instagram (Apify)",  "channel": "social",  "multiplier": 0.75},
    "whatsapp":     {"label": "WhatsApp",           "channel": "direct",  "multiplier": 0.8},
    "meta_ads":     {"label": "Meta Ads",           "channel": "paid",    "multiplier": 1.0},
    "google_ads":   {"label": "Google Ads",         "channel": "paid",    "multiplier": 1.0},
    "paid_traffic": {"label": "Tráfego Pago",       "channel": "paid",    "multiplier": 1.0},
    "manual":       {"label": "Entrada Manual",     "channel": "manual",  "multiplier": 0.5},
}


# ── Sweep state (in-memory, por processo) ─────────────────────────────────────

sweep_jobs: dict[str, dict] = {}

SWEEP_PROMPT = """Você avalia a compatibilidade entre um lead e uma oferta comercial específica.

Oferta:
- Descrição: {offer_description}
- Perfil ideal do cliente: {ideal_customer_profile}
- Ticket / Porte: {ticket}

Perfil do lead:
{lead_profile}

Avalie a compatibilidade e responda EXCLUSIVAMENTE em JSON válido, sem markdown:
{{
  "score": número de 0 a 100,
  "channel": "whatsapp" | "instagram_dm" | "nurture",
  "tone": "direto" | "educativo" | "prova_social" | "urgencia",
  "time": "HH:mm–HH:mm",
  "reason": "uma frase curta explicando a nota",
  "insufficient_data": true ou false
}}"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _placeholder_email(name: str) -> str:
    return f"{_slug(name)}.{uuid4().hex[:6]}@maps.placeholder.com"


def _esc_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _temperature_emoji(temperature: str | None) -> str:
    return {"HOT": "🔥", "WARM": "🌡️", "COLD": "🧊"}.get(temperature or "", "❓")


async def _ensure_source(session: AsyncSession, source_name: str) -> SourceORM:
    result = await session.execute(select(SourceORM).where(SourceORM.name == source_name))
    source = result.scalar_one_or_none()
    if source is None:
        defaults = SOURCE_DEFAULTS.get(source_name, {"label": source_name, "channel": "manual", "multiplier": 0.5})
        source = SourceORM(
            id=uuid4(),
            name=source_name,
            label=defaults["label"],
            channel=defaults["channel"],
            base_score_multiplier=defaults["multiplier"],
            is_active=True,
            created_at=datetime.utcnow(),
        )
        session.add(source)
        await session.flush()
        logger.info("source_auto_created", source_name=source_name)
    return source


def _build_lead_response(row: LeadORM) -> dict:
    meta = row.metadata_ or {}
    score_obj = row.scores[0] if row.scores else None
    return {
        "id":          str(row.id),
        "nome":        row.name,
        "email":       row.email,
        "whatsapp":    row.phone,
        "origem":      row.source_rel.name if row.source_rel else "unknown",
        "localizacao": meta.get("localizacao"),
        "stage":       BACKEND_TO_PIPELINE_STAGE.get(row.status, "capturado"),
        "score":       round(score_obj.score, 1) if score_obj else None,
        "temperature": score_obj.temperature if score_obj else None,
        "campanha_id": str(row.campanha_id) if row.campanha_id else None,
        "offer_tags":  row.offer_tags or [],
        "created_at":  row.created_at.isoformat(),
    }


async def _publish_lead(lead: Lead) -> None:
    event = LeadCapturedEvent(lead=lead)
    await publisher.publish("lead.captured", event.model_dump(mode="json"))


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global publisher
    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    await publisher.connect()
    logger.info("api_service_started")
    yield
    if publisher:
        await publisher.close()
    await engine.dispose()


# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(title="Lead Generator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request schemas ────────────────────────────────────────────────────────────

class LeadImportRequest(BaseModel):
    nome: str
    origem: str = "manual"
    whatsapp: str | None = None
    localizacao: str | None = None
    campanha_id: str | None = None
    email: str | None = None
    empresa: str | None = None


class LeadStatusUpdate(BaseModel):
    stage: str


class OfferItem(BaseModel):
    slug: str
    description: str
    icp: str = ""
    ticket: str = ""


class CampanhaWriteRequest(BaseModel):
    name: str
    offer_description: str | None = None
    ideal_customer_profile: str | None = None
    ticket: str | None = None
    focus_segments: list[str] = []
    offers: list[OfferItem] = []
    offer_operator: str = "OR"
    compatibility_threshold: int = 70
    max_leads_per_sweep: int = 500


# ── Lead endpoints ─────────────────────────────────────────────────────────────

@app.post("/leads", status_code=201)
async def import_lead(body: LeadImportRequest):
    """Importa um lead único e publica no pipeline."""
    source_name = ORIGIN_TO_SOURCE.get(body.origem.lower(), body.origem.lower())
    email = body.email or _placeholder_email(body.nome)
    campanha_id: UUID | None = None
    if body.campanha_id:
        try:
            campanha_id = UUID(body.campanha_id)
        except ValueError:
            pass

    async with AsyncSessionLocal() as session:
        async with session.begin():
            source = await _ensure_source(session, source_name)
            lead = Lead(
                name=body.nome,
                email=email,
                phone=body.whatsapp,
                company=body.empresa,
                source_id=source.id,
                source_name=source.name,
                campanha_id=campanha_id,
                status=LeadStatus.CAPTURED,
                metadata={"localizacao": body.localizacao} if body.localizacao else {},
            )

    await _publish_lead(lead)
    logger.info("lead_imported", lead_id=str(lead.id), source=source_name)
    return {"id": str(lead.id), "status": "queued"}


@app.post("/leads/csv", status_code=201)
async def import_csv(
    file: UploadFile = File(...),
    campanha_id: str | None = Form(None),
    origem: str = Form("csv"),
):
    """
    Importa leads em lote via arquivo CSV.
    Colunas esperadas: nome, email (opt), whatsapp (opt), empresa (opt), localizacao (opt)
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handles BOM from Excel
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    source_name = ORIGIN_TO_SOURCE.get(origem.lower(), "csv_import")
    camp_uuid: UUID | None = None
    if campanha_id:
        try:
            camp_uuid = UUID(campanha_id)
        except ValueError:
            pass

    reader = csv.DictReader(io.StringIO(text))
    # Normalize headers: strip spaces, lowercase
    if reader.fieldnames is None:
        raise HTTPException(status_code=422, detail="CSV vazio ou sem cabeçalho")

    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

    # Accept common column name variations
    FIELD_ALIASES: dict[str, list[str]] = {
        "nome":        ["nome", "name", "razao_social", "empresa_nome"],
        "email":       ["email", "e-mail", "email_contato"],
        "whatsapp":    ["whatsapp", "telefone", "phone", "celular", "fone"],
        "empresa":     ["empresa", "company", "negocio"],
        "localizacao": ["localizacao", "endereco", "address", "cidade"],
    }

    def get_field(row: dict, field: str) -> str | None:
        for alias in FIELD_ALIASES.get(field, [field]):
            if alias in row and row[alias].strip():
                return row[alias].strip()
        return None

    queued = 0
    errors = []

    async with AsyncSessionLocal() as session:
        async with session.begin():
            source = await _ensure_source(session, source_name)

    for i, row in enumerate(reader, start=2):  # start=2 accounts for header row
        nome = get_field(row, "nome")
        if not nome:
            errors.append({"row": i, "reason": "campo 'nome' ausente"})
            continue

        lead = Lead(
            name=nome,
            email=get_field(row, "email") or _placeholder_email(nome),
            phone=get_field(row, "whatsapp"),
            company=get_field(row, "empresa"),
            source_id=source.id,
            source_name=source.name,
            campanha_id=camp_uuid,
            status=LeadStatus.CAPTURED,
            metadata={"localizacao": get_field(row, "localizacao")} if get_field(row, "localizacao") else {},
        )
        await _publish_lead(lead)
        queued += 1

    logger.info("csv_import_done", queued=queued, errors=len(errors), source=source_name)
    return {"queued": queued, "errors": errors}


@app.get("/leads")
async def list_leads(limit: int = 200, offset: int = 0):
    """Lista leads com score e stage do pipeline."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LeadORM)
            .options(selectinload(LeadORM.source_rel), selectinload(LeadORM.scores))
            .order_by(LeadORM.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        leads = result.scalars().all()
    return [_build_lead_response(r) for r in leads]


@app.patch("/leads/{lead_id}/stage", status_code=200)
async def update_lead_stage(lead_id: str, body: LeadStatusUpdate):
    """Atualiza manualmente o stage de um lead (apenas descartado permitido via UI)."""
    new_status = ALLOWED_MANUAL_STATUSES.get(body.stage)
    if not new_status:
        raise HTTPException(status_code=422, detail=f"Stage inválido ou não permitido: {body.stage}")
    try:
        lid = UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="lead_id inválido")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(LeadORM).where(LeadORM.id == lid))
        lead = result.scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead não encontrado")
        lead.status = new_status.value
        await session.commit()

    return {"id": lead_id, "stage": body.stage}


# ── Sweep helpers ─────────────────────────────────────────────────────────────

def _build_sweep_lead_profile(lead: LeadORM, score_obj: "ScoreORM | None") -> str:
    lines = [
        f"Nome: {lead.name}",
        f"Telefone: {lead.phone or 'não informado'}",
        f"Score qualidade: {round(score_obj.score, 1) if score_obj else '—'} ({score_obj.temperature if score_obj else '—'})",
    ]
    meta = lead.metadata_ or {}
    if meta.get("search_tag"):
        lines.append(f"Tag de pesquisa: #{meta['search_tag']}")
    if meta.get("address"):
        lines.append(f"Endereço: {meta['address']}")
    if meta.get("rating"):
        lines.append(f"Avaliação Google: {meta['rating']} ⭐ ({meta.get('reviews', 0)} reviews)")
    if lead.instagram_username:
        lines.append(f"Instagram: @{lead.instagram_username}")
    if lead.instagram_followers:
        lines.append(f"Seguidores: {lead.instagram_followers:,}")
    if lead.instagram_engagement_rate:
        lines.append(f"Engajamento: {lead.instagram_engagement_rate:.1f}%")
    if lead.instagram_account_type:
        lines.append(f"Tipo de conta: {lead.instagram_account_type}")
    if lead.instagram_bio:
        lines.append(f"Bio: {lead.instagram_bio[:200]}")
    return "\n".join(lines)


async def _call_openai_sweep_offer(offer: dict, lead: LeadORM, score_obj: "ScoreORM | None") -> dict | None:
    if not settings.openai_api_key:
        return None
    try:
        prompt = SWEEP_PROMPT.format(
            offer_description=offer.get("description") or "não definida",
            ideal_customer_profile=offer.get("icp") or "não definido",
            ticket=offer.get("ticket") or "não informado",
            lead_profile=_build_sweep_lead_profile(lead, score_obj),
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                json={
                    "model": settings.openai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return json.loads(data["choices"][0]["message"]["content"])
    except Exception as exc:
        logger.error("sweep_openai_failed", error=str(exc))
        return None


def _fallback_sweep(lead: LeadORM, score_obj: "ScoreORM | None") -> dict:
    score = score_obj.score if score_obj else 0
    temperature = score_obj.temperature if score_obj else "COLD"
    has_phone = bool(lead.phone)
    has_instagram = bool(lead.instagram_username)
    compat = round(score * 0.8, 1)
    channel = "whatsapp" if has_phone and temperature in ("HOT", "WARM") else ("instagram_dm" if has_instagram else "nurture")
    return {
        "score": compat,
        "channel": channel,
        "tone": "direto" if temperature == "HOT" else "educativo",
        "time": "19h–21h",
        "reason": "análise determinística — OPENAI_API_KEY não configurado",
        "insufficient_data": score == 0 or (not has_phone and not has_instagram),
    }


async def _run_sweep(job_id: str, campanha_id: UUID) -> None:
    job = sweep_jobs[job_id]
    try:
        async with AsyncSessionLocal() as session:
            camp_result = await session.execute(select(CampaignORM).where(CampaignORM.id == campanha_id))
            campaign = camp_result.scalar_one_or_none()
        if not campaign:
            job["status"] = "error"
            job["error"] = "Campanha não encontrada"
            return

        # Resolve effective offers: multi-offer list takes priority, fall back to legacy single-offer
        if campaign.offers:
            offers = campaign.offers
        else:
            offers = [{
                "slug": campaign.slug,
                "description": campaign.offer_description or "",
                "icp": campaign.ideal_customer_profile or "",
                "ticket": campaign.ticket or "",
            }]

        threshold = campaign.compatibility_threshold
        operator = (campaign.offer_operator or "OR").upper()
        max_leads = campaign.max_leads_per_sweep
        offer_slugs = {o.get("slug", campaign.slug) for o in offers}

        async with AsyncSessionLocal() as session:
            q = select(LeadORM.id)
            if campaign.focus_segments:
                conditions = [LeadORM.metadata_["search_tag"].astext == seg for seg in campaign.focus_segments]
                q = q.where(or_(*conditions))
            else:
                q = q.where(LeadORM.status == LeadStatus.SCORED.value)
            q = q.limit(max_leads)
            result = await session.execute(q)
            lead_ids = [row[0] for row in result.all()]

        job["total"] = len(lead_ids)

        for lead_id in lead_ids:
            while job["status"] == "paused":
                await asyncio.sleep(2)
            if job["status"] != "running":
                break

            async with AsyncSessionLocal() as session:
                lead_result = await session.execute(
                    select(LeadORM).options(selectinload(LeadORM.scores)).where(LeadORM.id == lead_id)
                )
                lead = lead_result.scalar_one_or_none()
                if not lead:
                    job["analyzed"] += 1
                    continue

                existing_tags = list(lead.offer_tags or [])
                existing_slugs = {t.get("offer_slug") for t in existing_tags}
                score_obj = lead.scores[0] if lead.scores else None

                new_tags: list[dict] = []
                for offer in offers:
                    offer_slug = offer.get("slug") or campaign.slug
                    if offer_slug in existing_slugs:
                        continue
                    result_dict = await _call_openai_sweep_offer(offer, lead, score_obj) or _fallback_sweep(lead, score_obj)
                    new_tags.append({
                        "offer_slug": offer_slug,
                        "score": result_dict.get("score", 0),
                        "channel": result_dict.get("channel", "nurture"),
                        "tone": result_dict.get("tone", "educativo"),
                        "time": result_dict.get("time", "—"),
                        "reason": result_dict.get("reason", ""),
                        "insufficient_data": bool(result_dict.get("insufficient_data", False)),
                        "analyzed_at": datetime.utcnow().isoformat(),
                    })

                if new_tags:
                    lead.offer_tags = existing_tags + new_tags
                    flag_modified(lead, "offer_tags")
                    await session.commit()

                # AND/OR compatibility across all offers for this campaign
                all_offer_tags = [t for t in (existing_tags + new_tags) if t.get("offer_slug") in offer_slugs]
                offer_scores = [t["score"] for t in all_offer_tags]
                if operator == "AND":
                    compatible = len(offer_scores) >= len(offers) and all(s >= threshold for s in offer_scores)
                else:
                    compatible = any(s >= threshold for s in offer_scores)

                any_insufficient = any(t.get("insufficient_data") for t in new_tags)

            job["analyzed"] += 1
            if compatible:
                job["compatible"] += 1
            if any_insufficient:
                job["insufficient"] += 1

            for tag in new_tags:
                job["feed"] = ([{
                    "lead_name": lead.name,
                    "offer_slug": tag["offer_slug"],
                    "score": tag["score"],
                    "channel": tag["channel"],
                    "reason": tag["reason"],
                    "insufficient_data": tag["insufficient_data"],
                    "compatible": compatible,
                }] + job["feed"])[:20]

            await asyncio.sleep(0.5)

        job["status"] = "completed"
    except Exception as exc:
        logger.error("sweep_failed", job_id=job_id, error=str(exc))
        job["status"] = "error"
        job["error"] = str(exc)


# ── Analytics endpoints ────────────────────────────────────────────────────────

@app.get("/api/overview")
async def get_overview():
    """Métricas gerais do pipeline."""
    async with AsyncSessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(LeadORM))).scalar_one()
        scored = (
            await session.execute(
                select(func.count()).select_from(LeadORM).where(LeadORM.status == "scored")
            )
        ).scalar_one()
        avg_score = (await session.execute(select(func.avg(ScoreORM.score)))).scalar_one()
        hot_count = (
            await session.execute(
                select(func.count()).select_from(ScoreORM).where(ScoreORM.temperature == "HOT")
            )
        ).scalar_one()

    return {
        "total_leads":  total,
        "pontuados":    scored,
        "score_medio":  round(float(avg_score), 1) if avg_score else 0.0,
        "leads_hot":    hot_count,
    }


@app.get("/api/pipeline")
async def get_pipeline():
    """Contagem de leads por stage do pipeline."""
    stage_counts: dict[str, int] = {
        "capturado": 0, "validado": 0, "deduplicado": 0,
        "enriquecido": 0, "pontuado": 0, "descartado": 0,
    }
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LeadORM.status, func.count()).group_by(LeadORM.status)
        )
        for backend_status, count in result.all():
            stage = BACKEND_TO_PIPELINE_STAGE.get(backend_status)
            if stage and stage in stage_counts:
                stage_counts[stage] += count

    return stage_counts


@app.get("/api/pipeline/scores")
async def get_pipeline_scores():
    """Distribuição HOT/WARM/COLD para leads pontuados."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ScoreORM.temperature, func.count()).group_by(ScoreORM.temperature)
        )
        return {row[0]: row[1] for row in result.all()}


@app.get("/api/campanhas")
async def get_campanhas():
    """Lista campanhas ativas."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CampaignORM).where(CampaignORM.is_active == True).order_by(CampaignORM.name)
        )
        camps = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug,
            "status": c.status,
            "objective": c.objective,
            "offer_description": c.offer_description,
            "ideal_customer_profile": c.ideal_customer_profile,
            "ticket": c.ticket,
            "focus_segments": c.focus_segments or [],
            "offers": c.offers or [],
            "offer_operator": c.offer_operator or "OR",
            "compatibility_threshold": c.compatibility_threshold if c.compatibility_threshold is not None else 70,
            "max_leads_per_sweep": c.max_leads_per_sweep if c.max_leads_per_sweep is not None else 500,
        }
        for c in camps
    ]


@app.post("/api/campanhas/{campanha_id}/analisar", status_code=202)
async def analisar_campanha(campanha_id: str):
    """Dispara varredura de leads para uma campanha com oferta definida.

    Retorna job_id para acompanhar o progresso via GET /api/campanhas/{id}/progresso.
    A varredura roda em background — nunca re-analisa um lead já marcado para a mesma campanha.
    """
    try:
        camp_uuid = UUID(campanha_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="campanha_id inválido")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CampaignORM).where(CampaignORM.id == camp_uuid))
        campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    if not campaign.offers and not campaign.offer_description:
        raise HTTPException(status_code=422, detail="Campanha sem oferta definida — adicione ao menos uma oferta antes de analisar")

    for job in sweep_jobs.values():
        if job["campanha_id"] == campanha_id and job["status"] == "running":
            raise HTTPException(status_code=409, detail=f"Varredura já em andamento (job_id: {job['job_id']})")

    job_id = str(uuid4())
    sweep_jobs[job_id] = {
        "job_id": job_id,
        "campanha_id": campanha_id,
        "campanha_name": campaign.name,
        "status": "running",
        "total": 0,
        "analyzed": 0,
        "compatible": 0,
        "insufficient": 0,
        "feed": [],
        "started_at": datetime.utcnow().isoformat(),
        "error": None,
        "operator": (campaign.offer_operator or "OR").upper(),
        "threshold": campaign.compatibility_threshold if campaign.compatibility_threshold is not None else 70,
        "offers_count": len(campaign.offers) if campaign.offers else 1,
    }
    asyncio.create_task(_run_sweep(job_id, camp_uuid))
    logger.info("sweep_started", job_id=job_id, campanha=campaign.name)
    return {"job_id": job_id, "campanha_id": campanha_id, "status": "running"}


@app.get("/api/campanhas/{campanha_id}/progresso")
async def get_campanha_progresso(campanha_id: str):
    """Retorna o progresso da varredura mais recente de uma campanha."""
    matching = [j for j in sweep_jobs.values() if j["campanha_id"] == campanha_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Nenhuma varredura encontrada para esta campanha")
    return sorted(matching, key=lambda j: j["started_at"], reverse=True)[0]


@app.post("/api/jobs/{job_id}/pausar", status_code=200)
async def pausar_varredura(job_id: str):
    """Pausa uma varredura em andamento."""
    job = sweep_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job["status"] != "running":
        raise HTTPException(status_code=422, detail=f"Job não está em execução (status: {job['status']})")
    job["status"] = "paused"
    return {"job_id": job_id, "status": "paused"}


@app.post("/api/jobs/{job_id}/retomar", status_code=200)
async def retomar_varredura(job_id: str):
    """Retoma uma varredura pausada."""
    job = sweep_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job["status"] != "paused":
        raise HTTPException(status_code=422, detail=f"Job não está pausado (status: {job['status']})")
    job["status"] = "running"
    return {"job_id": job_id, "status": "running"}


# ── Action endpoints ───────────────────────────────────────────────────────────

@app.post("/api/leads/{lead_id}/telegram", status_code=200)
async def send_lead_to_telegram(lead_id: str):
    """Envia um lead manualmente para o canal Telegram configurado."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise HTTPException(status_code=503, detail="Telegram não configurado")
    try:
        lid = UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="lead_id inválido")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LeadORM)
            .options(selectinload(LeadORM.source_rel), selectinload(LeadORM.scores))
            .where(LeadORM.id == lid)
        )
        lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    score_obj = lead.scores[0] if lead.scores else None
    score = score_obj.score if score_obj else None
    temperature = score_obj.temperature if score_obj else "COLD"
    meta = lead.metadata_ or {}

    message = (
        f"{_temperature_emoji(temperature)} <b>Lead — {temperature}</b>\n\n"
        f"👤 <b>Nome:</b> {_esc_html(lead.name)}\n"
        f"📧 <b>Email:</b> {_esc_html(lead.email)}\n"
        f"📞 <b>Fone:</b> {_esc_html(lead.phone or '—')}\n"
        f"📍 <b>Local:</b> {_esc_html(meta.get('localizacao') or '—')}\n"
        f"📊 <b>Score:</b> <code>{f'{score:.1f}' if score is not None else '—'}/100</code>\n"
        f"🌐 <b>Fonte:</b> {_esc_html(lead.source_rel.name if lead.source_rel else 'N/A')}\n"
        f"🆔 <b>ID:</b> <code>{lead_id}</code>"
    )

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Falha no Telegram: {exc}")

    logger.info("lead_sent_telegram_manual", lead_id=lead_id, temperature=temperature)
    return {"sent": True, "lead_id": lead_id}


@app.get("/api/leads/{lead_id}/orchestration")
async def get_orchestration(lead_id: str):
    """Retorna a decisão IA mais recente para um lead."""
    try:
        lid = UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="lead_id inválido")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OrchestrationORM)
            .where(OrchestrationORM.lead_id == lid)
            .order_by(OrchestrationORM.decided_at.desc())
            .limit(1)
        )
        orch = result.scalar_one_or_none()

    if not orch:
        raise HTTPException(status_code=404, detail="Sem decisão IA para este lead")

    return {
        "need_identified": orch.need_identified,
        "offer":           orch.offer,
        "approach":        orch.approach,
        "tone":            orch.tone,
        "best_time":       orch.best_time,
        "score_adjustment": orch.score_adjustment,
        "final_score":     orch.final_score,
        "objections":      orch.objections,
        "opening_message": orch.opening_message,
        "reasoning":       orch.reasoning,
        "model_used":      orch.model_used,
        "decided_at":      orch.decided_at.isoformat(),
    }


@app.post("/api/campanhas", status_code=201)
async def create_campanha(body: CampanhaWriteRequest):
    """Cria uma nova campanha com suporte a múltiplas ofertas."""
    slug = _slug(body.name) or f"camp{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(CampaignORM).where(CampaignORM.slug == slug))).scalar_one_or_none()
        if existing:
            slug = f"{slug}{uuid4().hex[:4]}"
        camp = CampaignORM(
            id=uuid4(),
            name=body.name,
            slug=slug,
            status="active",
            is_active=True,
            offer_description=body.offer_description,
            ideal_customer_profile=body.ideal_customer_profile,
            ticket=body.ticket,
            focus_segments=body.focus_segments,
            offers=[o.model_dump() for o in body.offers],
            offer_operator=body.offer_operator.upper(),
            compatibility_threshold=body.compatibility_threshold,
            max_leads_per_sweep=body.max_leads_per_sweep,
            source_config={},
            created_at=datetime.utcnow(),
        )
        session.add(camp)
        await session.commit()
        await session.refresh(camp)
    logger.info("campanha_created", campanha_id=str(camp.id), name=camp.name)
    return {"id": str(camp.id), "slug": camp.slug, "name": camp.name}


@app.patch("/api/campanhas/{campanha_id}", status_code=200)
async def update_campanha(campanha_id: str, body: CampanhaWriteRequest):
    """Atualiza oferta(s) e configurações de uma campanha."""
    try:
        camp_uuid = UUID(campanha_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="campanha_id inválido")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CampaignORM).where(CampaignORM.id == camp_uuid))
        camp = result.scalar_one_or_none()
        if not camp:
            raise HTTPException(status_code=404, detail="Campanha não encontrada")
        camp.name = body.name
        camp.offer_description = body.offer_description
        camp.ideal_customer_profile = body.ideal_customer_profile
        camp.ticket = body.ticket
        camp.focus_segments = body.focus_segments
        camp.offers = [o.model_dump() for o in body.offers]
        camp.offer_operator = body.offer_operator.upper()
        camp.compatibility_threshold = body.compatibility_threshold
        camp.max_leads_per_sweep = body.max_leads_per_sweep
        flag_modified(camp, "offers")
        flag_modified(camp, "focus_segments")
        await session.commit()
    logger.info("campanha_updated", campanha_id=campanha_id)
    return {"id": campanha_id, "status": "updated"}


# ── Static (frontend dashboard) ────────────────────────────────────────────────

import os

_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    @app.get("/")
    async def serve_index():
        index_path = os.path.join(_static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="index.html não encontrado")
