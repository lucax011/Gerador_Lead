# Motor de Audiência

Plataforma B2B que refina potenciais clientes de qualquer nicho para uma oferta específica.

O operador busca leads via Google Places, enriquece com CNPJ.ws e Instagram, define uma campanha com oferta e perfil de cliente ideal, e o orquestrador IA analisa cada lead contra essa oferta — entregando `offer_tags` prontos para o bot de abordagem consumir.

**Princípio:** o score não é do lead — é da relação lead × oferta.

---

## Quickstart

```bash
# 1. Subir infraestrutura (PostgreSQL + RabbitMQ + workers)
cd lead-generator/infra
cp ../.env.example ../.env   # preencher TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENAI_API_KEY
docker compose up --build -d

# 2. Aplicar migrations
cd lead-generator
alembic -c shared/database/migrations/alembic.ini upgrade head

# 3. Acessar dashboard
# Motor de Audiência → http://localhost:8000
# pgAdmin           → http://localhost:5050  (admin@admin.com / admin)
# RabbitMQ          → http://localhost:15672 (guest / guest)
```

---

## Fluxo

```
Nova Pesquisa (Google Places)
        ↓ importar leads com tag do nicho
Validator → Deduplicator → Enricher (CNPJ.ws) → Scorer (qualidade 0–100)
        ↓
Orquestrador IA ← Campanha com oferta definida
(varre leads do banco, analisa lead × oferta, salva offer_tag)
        ↓
Banco de leads marcados → Bot de abordagem (sistema separado)
        ↓
Resultado (replied / converted / churned)
```

---

## Stack

Python 3.11 · FastAPI · RabbitMQ (aio-pika) · PostgreSQL 15 (asyncpg) · SQLAlchemy 2.0 · Pydantic v2 · Alembic · Docker Compose

---

## Estrutura

```
lead-generator/
├── shared/
│   ├── models/          # Pydantic: Lead, Campaign, Source, eventos
│   ├── database/        # SQLAlchemy ORM + migrations Alembic
│   └── broker/          # RabbitMQ publisher/consumer async
├── services/
│   ├── api/             # FastAPI + dashboard web (Motor de Audiência)
│   ├── scraper/         # Google Places API, Apify Instagram, web scraping
│   ├── validator/       # Regras de negócio (email, domínio, campos)
│   ├── deduplicator/    # Merge por LOWER(email)
│   ├── enricher/        # CNPJ.ws (ativo) · BigDataCorp · Serasa (stubs)
│   ├── scorer/          # Score 0–100 qualidade de dados
│   ├── orchestrator/    # GPT-4o-mini · modo event-driven + modo varredura
│   ├── distributor/     # Telegram com retry 3x
│   ├── outreach/        # WhatsApp (Evolution API) · Instagram DM (stub)
│   └── feedback/        # Bot Telegram /respondeu /convertido /churned
└── infra/
    └── docker-compose.yml
```

---

## Variáveis obrigatórias para MVP

| Variável | Para quê |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Distribuição de leads |
| `TELEGRAM_CHAT_ID` | Chat que recebe os leads |
| `OPENAI_API_KEY` | Orquestrador IA (sem key → fallback determinístico) |
| `GOOGLE_PLACES_API_KEY` | Nova Pesquisa — busca por nicho |

Ver [.env.example](lead-generator/.env.example) para lista completa.
