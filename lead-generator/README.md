# Gerador de Leads

Pipeline automatizado de captura, qualificação e distribuição de leads com
arquitetura Microservices + Event-Driven.

## Fluxo

```
Scraper → Validator → Deduplicator → Scorer → Distributor → Telegram
                                                     ↓ (erros)
                                              Dead-Letter Queue
```

## Pré-requisitos

- Docker 24+ e Docker Compose v2
- (Opcional para dev local) Python 3.11+

## Configuração Inicial

```bash
# 1. Clone e entre na pasta
cd lead-generator

# 2. Copie e edite as variáveis de ambiente
cp .env.example .env
# Edite .env e preencha TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCRAPER_TARGET_URLS

# 3. Suba a stack completa
cd infra
docker compose up --build
```

## Desenvolvimento com Hot-Reload

```bash
cd infra
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Publicar um Lead de Teste

Com a stack rodando, publique um lead diretamente no RabbitMQ:

```bash
docker compose exec scraper python -c "
import asyncio, json
from shared.broker.rabbitmq import RabbitMQPublisher
from shared.models.events import LeadCapturedEvent
from shared.models.lead import Lead, LeadSource

async def main():
    pub = RabbitMQPublisher('amqp://guest:guest@rabbitmq:5672/')
    await pub.connect()
    lead = Lead(
        name='Maria Oliveira',
        email='maria@techcorp.com.br',
        phone='+5511988887777',
        company='TechCorp',
        source=LeadSource.PAID_TRAFFIC,
    )
    event = LeadCapturedEvent(lead=lead)
    await pub.publish('lead.captured', event.model_dump(mode='json'))
    print('Publicado:', lead.id)
    await pub.close()

asyncio.run(main())
"
```

## Interfaces

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| RabbitMQ Management | http://localhost:15672 | guest / guest |
| PostgreSQL | localhost:5432 | lead_user / lead_secret |

## Migrations

```bash
# Gerar nova migration
alembic -c shared/database/migrations/alembic.ini revision --autogenerate -m "descricao"

# Aplicar migrations
alembic -c shared/database/migrations/alembic.ini upgrade head
```

## Estrutura

```
lead-generator/
├── shared/          # Código compartilhado entre workers
│   ├── config.py    # Configurações via pydantic-settings
│   ├── models/      # Pydantic: Lead, LeadStatus, Events
│   ├── broker/      # RabbitMQ Publisher e Consumer
│   └── database/    # SQLAlchemy ORM + migrations Alembic
├── services/
│   ├── scraper/     # Captura leads via web scraping
│   ├── validator/   # Valida email, telefone, campos obrigatórios
│   ├── deduplicator/# Detecta leads duplicados por email
│   ├── scorer/      # Pontua 0-100 (HOT/WARM/COLD)
│   └── distributor/ # Entrega via Telegram com emoji por temperatura
└── infra/
    ├── docker-compose.yml
    └── postgres/init.sql
```

## Score e Temperatura

| Temperatura | Score | Emoji |
|-------------|-------|-------|
| HOT | ≥ 70 | 🔥 |
| WARM | 40-69 | 🌡️ |
| COLD | < 40 | 🧊 |

Critérios de pontuação configuráveis via variáveis de ambiente (`SCORE_WEIGHT_*`).
