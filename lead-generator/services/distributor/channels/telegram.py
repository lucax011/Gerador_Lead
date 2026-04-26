import structlog

import httpx

logger = structlog.get_logger(__name__)

TEMPERATURE_EMOJI = {
    "HOT": "🔥",
    "WARM": "🌡️",
    "COLD": "🧊",
}

def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(lead: dict, score: float, temperature: str) -> str:
    emoji = TEMPERATURE_EMOJI.get(temperature, "❓")
    source_label = _esc(lead.get("source_name") or "N/A")
    phone = _esc(lead.get("phone") or "Não informado")
    company = _esc(lead.get("company") or "Não informada")
    name = _esc(lead["name"])
    email = _esc(lead["email"])

    instagram_line = ""
    if lead.get("instagram_username"):
        ig_user = _esc(lead["instagram_username"])
        followers = lead.get("instagram_followers") or 0
        instagram_line = f"\n📸 <b>Instagram:</b> @{ig_user} ({followers:,} seguidores)"

    return (
        f"{emoji} <b>Novo Lead — {temperature}</b>\n\n"
        f"👤 <b>Nome:</b> {name}\n"
        f"📧 <b>Email:</b> {email}\n"
        f"📞 <b>Telefone:</b> {phone}\n"
        f"🏢 <b>Empresa:</b> {company}\n"
        f"📊 <b>Score:</b> <code>{score:.1f}/100</code>\n"
        f"🌐 <b>Fonte:</b> {source_label}"
        f"{instagram_line}\n"
        f"🆔 <b>ID:</b> <code>{lead['id']}</code>"
    )


class TelegramChannel:
    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id
        self._client = httpx.AsyncClient(timeout=10)

    async def send(self, lead: dict, score: float, temperature: str) -> bool:
        message = format_message(lead, score, temperature)
        url = self.API_URL.format(token=self._token)
        try:
            response = await self._client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
            logger.info("Telegram message sent", lead_id=lead.get("id"), temperature=temperature)
            return True
        except httpx.HTTPError as exc:
            logger.error("Failed to send Telegram message", error=str(exc), lead_id=lead.get("id"))
            return False

    async def close(self) -> None:
        await self._client.aclose()
