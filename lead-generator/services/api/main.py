import csv
import io
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _placeholder_email(name: str) -> str:
    return f"{_slug(name)}.{uuid4().hex[:6]}@import.local"


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
        {"id": str(c.id), "name": c.name, "slug": c.slug, "status": c.status, "objective": c.objective}
        for c in camps
    ]


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
