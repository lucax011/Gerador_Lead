# Gerador de Leads — Contexto Persistente para Claude

## Visão Geral da Arquitetura

Pipeline event-driven de 5 estágios. Cada estágio é um worker Python independente
em container Docker que se comunica exclusivamente via RabbitMQ (exchange `leads`, type `TOPIC`).

```
[Scraper] --lead.captured--> [Validator] --lead.validated--> [Deduplicator]
    --lead.deduplicated--> [Scorer] --lead.scored--> [Distributor] --> Telegram
                                                             ↓ (falhas)
                                                      [Dead-Letter Queue]
```

## Decisões Técnicas

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| Mensageria | RabbitMQ TOPIC exchange | Permite múltiplos consumers por evento sem alterar producers |
| ORM | SQLAlchemy 2.0 async | API nativa async, type-safe com mapped_column |
| Validação | Pydantic v2 | Performance (Rust core), integração nativa com FastAPI |
| Logging | structlog | Logs estruturados (JSON-friendly), fácil correlação por lead_id |
| Dead-letter | Exchange FANOUT `lead.dlx` | Centraliza falhas sem acoplamento entre workers |
| Dedup | Unique index em LOWER(email) | Garante idempotência no banco sem lógica distribuída complexa |

## Routing Keys

| Evento | Routing Key | Publicado por | Consumido por |
|--------|-------------|--------------|---------------|
| Lead capturado | `lead.captured` | scraper | validator |
| Lead validado | `lead.validated` | validator | deduplicator |
| Lead deduplicado | `lead.deduplicated` | deduplicator | scorer |
| Lead pontuado | `lead.scored` | scorer | distributor |
| Lead rejeitado | `lead.rejected` | qualquer worker | (dead-letter) |

## Critérios de Score (0-100)

```
data_completeness  = peso 40  (name+email=mandatory, phone+company=optional)
source             = peso 25  (paid_traffic=100%, chatbot=70%, web_scraping=40%)
phone_present      = peso 20  (tem telefone → pontuação total)
email_domain       = peso 15  (corporativo=100%, trusted=60%, outros=30%)
```

Temperaturas: **HOT** ≥70 | **WARM** 40-69 | **COLD** <40

## Como Adicionar uma Nova Fonte de Leads

1. Adicionar valor ao enum `LeadSource` em [shared/models/lead.py](shared/models/lead.py)
2. Criar arquivo em `services/scraper/sources/minha_fonte.py` implementando método
   `async scrape(url) -> list[RawLead]`
3. Instanciar e chamar a nova fonte dentro de `scrape_and_publish()` em [services/scraper/main.py](services/scraper/main.py)
4. Adicionar peso da nova fonte em `_score_source()` de [services/scorer/scoring_engine.py](services/scorer/scoring_engine.py)
5. Nenhuma alteração nos outros workers é necessária

## Como Adicionar um Novo Canal de Distribuição

1. Criar `services/distributor/channels/meu_canal.py` com classe `MeuCanalChannel`
   implementando `async send(lead, score, temperature) -> bool`
2. Instanciar o canal em `main()` de [services/distributor/main.py](services/distributor/main.py)
3. Chamar `await meu_canal.send(...)` dentro de `handle_lead_scored()`
4. Adicionar variáveis de credenciais no `.env.example` e em `shared/config.py`

## Comandos do Dia a Dia

```bash
# Subir toda a stack
cd infra && docker compose up --build

# Subir em modo desenvolvimento (hot-reload)
cd infra && docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Ver logs de um worker específico
docker compose logs -f scorer

# Rodar apenas a infra (postgres + rabbitmq) para dev local
docker compose up postgres rabbitmq

# Criar nova migration Alembic
alembic -c shared/database/migrations/alembic.ini revision --autogenerate -m "descricao"

# Aplicar migrations
alembic -c shared/database/migrations/alembic.ini upgrade head

# Acessar RabbitMQ Management UI
open http://localhost:15672  # guest / guest

# Publicar lead de teste manualmente (com Python)
python -c "
import asyncio
from shared.broker.rabbitmq import RabbitMQPublisher
from shared.models.events import LeadCapturedEvent
from shared.models.lead import Lead, LeadSource
import json

async def main():
    pub = RabbitMQPublisher('amqp://guest:guest@localhost:5672/')
    await pub.connect()
    lead = Lead(name='João Silva', email='joao@empresa.com.br', phone='+5511999990000', source=LeadSource.PAID_TRAFFIC)
    event = LeadCapturedEvent(lead=lead)
    await pub.publish('lead.captured', event.model_dump(mode='json'))
    print('Lead publicado:', lead.id)
    await pub.close()

asyncio.run(main())
"
```

## Estrutura de Filas no RabbitMQ

Cada consumer cria sua própria fila e a vincula ao exchange `leads`:

- `validator.lead.captured` → routing_key `lead.captured`
- `deduplicator.lead.validated` → routing_key `lead.validated`
- `scorer.lead.deduplicated` → routing_key `lead.deduplicated`
- `distributor.lead.scored` → routing_key `lead.scored`
- `lead.rejected` → exchange fanout `lead.dlx` (dead-letter)

## Variáveis de Ambiente Críticas

Ver [.env.example](.env.example) para lista completa. As mais importantes:

- `RABBITMQ_URL` — URL de conexão com RabbitMQ
- `DATABASE_URL` — URL async para PostgreSQL (usa `asyncpg`)
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — credenciais do bot
- `SCRAPER_TARGET_URLS` — URLs separadas por vírgula para scraping
- `HOT_SCORE_THRESHOLD` / `WARM_SCORE_THRESHOLD` — limites de temperatura
