"""Feedback Worker

Bot Telegram que recebe comandos manuais e atualiza o status do lead no banco.

Comandos disponíveis:
  /respondeu <lead_id>   — lead respondeu ao contato
  /convertido <lead_id>  — lead virou cliente
  /churned <lead_id>     — lead frio, sem retorno

Usa getUpdates (polling) — não precisa de URL pública.
"""
import asyncio
import logging
import sys
from pathlib import Path
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config import get_settings
from shared.database.models import LeadORM
from shared.database.session import AsyncSessionLocal
from shared.models.lead import LeadStatus

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
)
log = structlog.get_logger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

COMMANDS: dict[str, LeadStatus] = {
    "/respondeu": LeadStatus.REPLIED,
    "/convertido": LeadStatus.CONVERTED,
    "/churned": LeadStatus.CHURNED,
}

STATUS_LABEL: dict[LeadStatus, str] = {
    LeadStatus.REPLIED: "✅ Respondeu",
    LeadStatus.CONVERTED: "🏆 Convertido",
    LeadStatus.CHURNED: "🚫 Churned",
}

# Transições válidas — impede regressão no lifecycle
VALID_TRANSITIONS: dict[LeadStatus, set[LeadStatus]] = {
    LeadStatus.DISTRIBUTED: {LeadStatus.REPLIED, LeadStatus.CHURNED},
    LeadStatus.CONTACTED:   {LeadStatus.REPLIED, LeadStatus.CHURNED},
    LeadStatus.REPLIED:     {LeadStatus.CONVERTED, LeadStatus.CHURNED},
    LeadStatus.CONVERTED:   set(),
    LeadStatus.CHURNED:     set(),
}


async def send_message(chat_id: int | str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )


async def get_updates(offset: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=35) as client:
        try:
            response = await client.get(
                f"{TELEGRAM_API}/getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
            )
            response.raise_for_status()
            return response.json().get("result", [])
        except httpx.HTTPError as exc:
            log.warning("getUpdates error", error=str(exc))
            return []


async def handle_command(chat_id: int | str, command: str, lead_id_str: str) -> None:
    new_status = COMMANDS[command]

    try:
        lead_uuid = UUID(lead_id_str)
    except ValueError:
        await send_message(chat_id, f"❌ ID inválido: <code>{lead_id_str}</code>")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(LeadORM).where(LeadORM.id == lead_uuid))
        lead = result.scalar_one_or_none()

        if lead is None:
            await send_message(chat_id, f"❌ Lead não encontrado: <code>{lead_id_str}</code>")
            return

        current = LeadStatus(lead.status)
        allowed = VALID_TRANSITIONS.get(current, set())

        if new_status not in allowed:
            await send_message(
                chat_id,
                f"⚠️ Transição inválida: <b>{current.value}</b> → <b>{new_status.value}</b>\n"
                f"Lead <code>{lead_id_str[:8]}…</code> está em <b>{current.value}</b>.",
            )
            return

        await session.execute(
            update(LeadORM).where(LeadORM.id == lead_uuid).values(status=new_status)
        )
        await session.commit()

    label = STATUS_LABEL[new_status]
    log.info("Lead status updated", lead_id=lead_id_str, status=new_status.value)
    await send_message(
        chat_id,
        f"{label} — <b>{lead.name}</b>\n"
        f"<code>{lead_id_str}</code>\n"
        f"Status: <b>{new_status.value}</b>",
    )


async def process_update(update_data: dict) -> None:
    message = update_data.get("message", {})
    text = (message.get("text") or "").strip()
    chat_id = message.get("chat", {}).get("id")

    if not text or not chat_id:
        return

    parts = text.split()
    command = parts[0].lower().split("@")[0]  # remove @botname se presente

    if command not in COMMANDS:
        if command.startswith("/"):
            await send_message(
                chat_id,
                "📋 <b>Comandos disponíveis:</b>\n"
                "/respondeu <code>&lt;lead_id&gt;</code>\n"
                "/convertido <code>&lt;lead_id&gt;</code>\n"
                "/churned <code>&lt;lead_id&gt;</code>",
            )
        return

    if len(parts) < 2:
        await send_message(chat_id, f"❌ Uso: <code>{command} &lt;lead_id&gt;</code>")
        return

    await handle_command(chat_id, command, parts[1])


async def main() -> None:
    if not settings.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN não configurado — feedback worker encerrado")
        return

    log.info("Feedback worker iniciado (polling getUpdates)")
    offset = 0

    while True:
        updates = await get_updates(offset)
        for upd in updates:
            offset = upd["update_id"] + 1
            try:
                await process_update(upd)
            except Exception as exc:
                log.error("Erro ao processar update", update_id=upd.get("update_id"), error=str(exc))

        if not updates:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
