"""Evolution API — canal WhatsApp para abordagem automatizada.

Requer Evolution API self-hosted (https://github.com/EvolutionAPI/evolution-api).
Configurar: EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE no .env.

Instância deve estar conectada a um número WhatsApp real e ativo.
"""
import httpx
import structlog

log = structlog.get_logger(__name__)


def _format_phone(phone: str) -> str:
    """Normaliza telefone para formato E.164 sem + (55119...) ."""
    import re
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        digits = digits[1:]
    if not digits.startswith("55"):
        digits = "55" + digits
    return digits


class WhatsAppChannel:
    def __init__(self, api_url: str, api_key: str, instance: str) -> None:
        self._base = api_url.rstrip("/")
        self._key = api_key
        self._instance = instance
        self._headers = {
            "apikey": api_key,
            "Content-Type": "application/json",
        }

    async def send_text(self, phone: str, message: str) -> dict:
        """Envia mensagem de texto via Evolution API."""
        number = _format_phone(phone)
        url = f"{self._base}/message/sendText/{self._instance}"
        payload = {
            "number": number,
            "text": message,
            "delay": 1200,  # simula digitação (ms)
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, headers=self._headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                log.info("WhatsApp sent", phone=number[:8] + "***", message_id=data.get("key", {}).get("id"))
                return {"success": True, "external_id": data.get("key", {}).get("id"), "data": data}
        except httpx.HTTPStatusError as e:
            log.error("WhatsApp HTTP error", status=e.response.status_code, body=e.response.text[:200])
            return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:100]}"}
        except Exception as e:
            log.error("WhatsApp send failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def check_number(self, phone: str) -> bool:
        """Verifica se o número tem WhatsApp ativo."""
        number = _format_phone(phone)
        url = f"{self._base}/chat/whatsappNumbers/{self._instance}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url, headers=self._headers,
                    json={"numbers": [number]},
                )
                data = resp.json()
                results = data if isinstance(data, list) else []
                for r in results:
                    if r.get("exists"):
                        return True
                return False
        except Exception:
            return True  # assume válido se não conseguir checar
