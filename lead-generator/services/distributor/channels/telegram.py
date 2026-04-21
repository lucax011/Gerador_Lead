import logging

import httpx

logger = logging.getLogger(__name__)

TEMPERATURE_EMOJI = {
    "HOT": "🔥",
    "WARM": "🌡️",
    "COLD": "🧊",
}

SOURCE_LABEL = {
    "web_scraping": "Web Scraping",
    "chatbot": "Chatbot",
    "paid_traffic": "Tráfego Pago",
}


def format_message(lead: dict, score: float, temperature: str) -> str:
    emoji = TEMPERATURE_EMOJI.get(temperature, "❓")
    source_label = SOURCE_LABEL.get(lead.get("source", ""), lead.get("source", "N/A"))
    phone = lead.get("phone") or "Não informado"
    company = lead.get("company") or "Não informada"

    return (
        f"{emoji} *Novo Lead — {temperature}*\n\n"
        f"👤 *Nome:* {lead['name']}\n"
        f"📧 *Email:* {lead['email']}\n"
        f"📞 *Telefone:* {phone}\n"
        f"🏢 *Empresa:* {company}\n"
        f"📊 *Score:* `{score:.1f}/100`\n"
        f"🌐 *Fonte:* {source_label}\n"
        f"🆔 *ID:* `{lead['id']}`"
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
                    "parse_mode": "Markdown",
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
