import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.broker.rabbitmq import RabbitMQPublisher
from shared.config import get_settings
from shared.database.models import CampaignORM, LeadORM, ScoreORM, SourceORM
from shared.models.events import LeadCapturedEvent
from shared.models.lead import Lead, LeadStatus

logger = structlog.get_logger(__name__)
settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

publisher: RabbitMQPublisher | None = None

ORIGIN_TO_SOURCE = {
    "maps": "google_maps",
    "instagram": "instagram",
    "csv": "csv_import",
    "whatsapp": "whatsapp",
    "meta": "meta_ads",
    "google": "google_ads",
    "paid": "paid_traffic",
}

FRONTEND_TO_BACKEND_STATUS = {
    "novo": LeadStatus.CAPTURED,
    "abordado": LeadStatus.CONTACTED,
    "respondeu": LeadStatus.REPLIED,
    "qualificado": LeadStatus.SCORED,
    "convertido": LeadStatus.CONVERTED,
    "descartado": LeadStatus.CHURNED,
}

BACKEND_TO_FRONTEND_STATUS = {
    LeadStatus.CAPTURED.value: "novo",
    LeadStatus.VALIDATED.value: "novo",
    LeadStatus.DEDUPLICATED.value: "novo",
    LeadStatus.ENRICHED.value: "novo",
    LeadStatus.SCORED.value: "qualificado",
    LeadStatus.DISTRIBUTED.value: "qualificado",
    LeadStatus.CONTACTED.value: "abordado",
    LeadStatus.REPLIED.value: "respondeu",
    LeadStatus.CONVERTED.value: "convertido",
    LeadStatus.CHURNED.value: "descartado",
    LeadStatus.REJECTED.value: "descartado",
}


async def ensure_source(session: AsyncSession, source_name: str) -> SourceORM | None:
    result = await session.execute(select(SourceORM).where(SourceORM.name == source_name))
    source = result.scalar_one_or_none()
    if source is None:
        label_map = {
            "google_maps": "Google Maps",
            "csv_import": "Importação CSV",
            "instagram": "Instagram",
            "whatsapp": "WhatsApp",
            "meta_ads": "Meta Ads",
            "google_ads": "Google Ads",
            "paid_traffic": "Tráfego Pago",
        }
        multiplier_map = {
            "google_maps": 0.9,
            "csv_import": 0.6,
            "instagram": 0.75,
            "whatsapp": 0.8,
            "meta_ads": 1.0,
            "google_ads": 1.0,
            "paid_traffic": 1.0,
        }
        source = SourceORM(
            id=uuid4(),
            name=source_name,
            label=label_map.get(source_name, source_name),
            channel="manual",
            base_score_multiplier=multiplier_map.get(source_name, 0.5),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        session.add(source)
        await session.flush()
        logger.info("Source auto-created", source_name=source_name)
    return source


@asynccontextmanager
async def lifespan(app: FastAPI):
    global publisher
    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    await publisher.connect()
    logger.info("API service started")
    yield
    if publisher:
        await publisher.close()
    await engine.dispose()


app = FastAPI(title="Lead Generator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ─────────────────────────────────────────────────

class LeadImportRequest(BaseModel):
    nome: str
    origem: str = "maps"
    whatsapp: str | None = None
    localizacao: str | None = None
    status: str = "novo"
    campanha_id: str | None = None
    score_nichochat: float | None = None
    score_consorcio: float | None = None
    email: str | None = None


class LeadResponse(BaseModel):
    id: str
    nome: str
    email: str
    whatsapp: str | None
    origem: str
    localizacao: str | None
    status: str
    score: float | None
    campanha_id: str | None
    created_at: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _placeholder_email(name: str) -> str:
    return f"{_slug(name)}.{uuid4().hex[:6]}@maps.import"


def _lead_response(row: LeadORM) -> dict:
    meta = row.metadata_ or {}
    return {
        "id": str(row.id),
        "nome": row.name,
        "email": row.email,
        "whatsapp": row.phone,
        "origem": row.source_rel.name if row.source_rel else "unknown",
        "localizacao": meta.get("localizacao"),
        "status": BACKEND_TO_FRONTEND_STATUS.get(row.status, "novo"),
        "score": row.scores[0].score if row.scores else None,
        "campanha_id": str(row.campanha_id) if row.campanha_id else None,
        "created_at": row.created_at.isoformat(),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/leads", status_code=201)
async def import_lead(body: LeadImportRequest):
    source_name = ORIGIN_TO_SOURCE.get(body.origem.lower(), body.origem.lower())
    email = body.email if body.email else _placeholder_email(body.nome)
    campanha_id: UUID | None = None
    if body.campanha_id:
        try:
            campanha_id = UUID(body.campanha_id)
        except ValueError:
            pass

    async with AsyncSessionLocal() as session:
        async with session.begin():
            source = await ensure_source(session, source_name)
            lead = Lead(
                name=body.nome,
                email=email,
                phone=body.whatsapp,
                source_id=source.id,
                source_name=source.name,
                campanha_id=campanha_id,
                status=LeadStatus.CAPTURED,
                metadata={"localizacao": body.localizacao} if body.localizacao else {},
            )

    event = LeadCapturedEvent(lead=lead)
    await publisher.publish("lead.captured", event.model_dump(mode="json"))
    logger.info("Lead imported via API", lead_id=str(lead.id), source=source_name)

    return {"id": str(lead.id), "status": "queued"}


@app.get("/leads")
async def list_leads(limit: int = 100, offset: int = 0):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LeadORM)
            .join(LeadORM.source_rel)
            .outerjoin(LeadORM.scores)
            .order_by(LeadORM.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        leads = result.unique().scalars().all()
    return [_lead_response(r) for r in leads]


@app.get("/api/overview")
async def overview():
    async with AsyncSessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(LeadORM))).scalar_one()
        converted = (
            await session.execute(
                select(func.count()).select_from(LeadORM).where(LeadORM.status == "converted")
            )
        ).scalar_one()
        avg_score = (
            await session.execute(select(func.avg(ScoreORM.score)))
        ).scalar_one()

    return {
        "total_leads": total,
        "convertidos": converted,
        "score_medio": round(float(avg_score), 1) if avg_score else 0.0,
        "taxa_conversao": round(converted / total * 100, 1) if total else 0.0,
    }


@app.get("/api/pipeline")
async def pipeline():
    frontend_statuses = list(FRONTEND_TO_BACKEND_STATUS.keys())
    counts: dict[str, int] = {s: 0 for s in frontend_statuses}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LeadORM.status, func.count()).group_by(LeadORM.status)
        )
        for backend_status, count in result.all():
            frontend = BACKEND_TO_FRONTEND_STATUS.get(backend_status, "novo")
            counts[frontend] = counts.get(frontend, 0) + count

    return counts


@app.get("/api/campanhas")
async def campanhas():
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
        }
        for c in camps
    ]


# ── Static files (frontend dashboard) ─────────────────────────────────────────
import os

_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    @app.get("/")
    async def serve_index():
        index = os.path.join(_static_dir, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="index.html not found")
