from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "lead_generator"
    postgres_user: str = "lead_user"
    postgres_password: str = "lead_secret"
    database_url: str = "postgresql+asyncpg://lead_user:lead_secret@postgres:5432/lead_generator"

    # RabbitMQ
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_vhost: str = "/"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Scraper
    scraper_target_urls: str = ""
    scraper_interval_seconds: int = 300
    scraper_user_agent: str = "Mozilla/5.0 (compatible; LeadBot/1.0)"

    # Scoring weights (must sum to 100)
    score_weight_data_completeness: int = 40
    score_weight_source: int = 25
    score_weight_phone_present: int = 20
    score_weight_email_domain: int = 15

    # Distributor thresholds
    hot_score_threshold: int = 70
    warm_score_threshold: int = 40

    # Apify / Instagram
    apify_token: str | None = None
    instagram_usernames: str = ""

    # Enricher
    bigdatacorp_token: str | None = None       # BigDataCorp API token (pago)
    serasa_client_id: str | None = None        # Serasa/Experian API (pago)
    serasa_client_secret: str | None = None
    cnpjws_enabled: bool = True                # CNPJ.ws é gratuito

    # Orchestrator IA
    openai_api_key: str | None = None          # GPT-4o-mini
    openai_model: str = "gpt-4o-mini"
    orchestrator_enabled: bool = True          # desativar para usar apenas score base

    # Outreach
    evolution_api_url: str = ""                # http://evolution-api:8080
    evolution_api_key: str = ""
    evolution_instance: str = ""              # nome da instância WhatsApp conectada
    outreach_enabled: bool = False             # só ativa quando Evolution API estiver configurada
    outreach_delay_seconds: int = 5            # delay entre envios em lote
    instagram_dm_enabled: bool = False         # Instagram DM (requer conta conectada)

    # General
    log_level: str = "INFO"
    environment: str = "development"

    @property
    def scraper_urls_list(self) -> list[str]:
        return [u.strip() for u in self.scraper_target_urls.split(",") if u.strip()]

    @property
    def instagram_usernames_list(self) -> list[str]:
        return [u.strip() for u in self.instagram_usernames.split(",") if u.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
