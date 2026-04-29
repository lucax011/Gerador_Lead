# Motor de Audiência — Documentação Técnica

## Visão Geral

Plataforma B2B que refina potenciais clientes de qualquer nicho para uma oferta específica. O operador busca leads via Google Places, enriquece com CNPJ.ws e Instagram, executa o orquestrador IA contra uma oferta definida, e o banco de leads sai com `offer_tags` prontos para o bot de abordagem consumir.

**Princípio central:** score não é do lead — é da relação lead × oferta. Um lead pode ter 98 pts para "bot de automação MEI" e 40 pts para "consórcio R$ 200k".

---

## Arquitetura

```
  Dashboard Web (Motor de Audiência)
  http://localhost:8000
         │
         │  POST /leads   GET /leads   GET /api/*
         │  POST /api/campanhas/{id}/analisar  ← modo varredura
         ▼
  ┌──────────────────────────────────────────────────────────┐
  │  API FastAPI  (services/api/)                            │
  │  · Serve static/index.html                              │
  │  · Publica lead.captured → RabbitMQ                      │
  │  · Dispara varredura do orchestrator por campanha        │
  └──────────────────┬───────────────────────────────────────┘
                     │ lead.captured
                     ▼
  Validator → Deduplicator → Enricher → Scorer → Orchestrator (event-driven)
                                                      ↓
                                                  Distributor → Telegram
                                                      ↓
                                                  Outreach → WhatsApp / DM
```

### Routing keys RabbitMQ (TOPIC exchange "leads")

| Evento | Publicador | Consumidor |
|--------|-----------|-----------|
| `lead.captured` | API, Scraper | Validator |
| `lead.validated` | Validator | Deduplicator |
| `lead.deduplicated` | Deduplicator | Enricher |
| `lead.enriched` | Enricher | Scorer |
| `lead.scored` | Scorer | Orchestrator (event-driven), Distributor |
| `lead.orchestrated` | Orchestrator | Outreach |
| `lead.rejected` | Validator | DLQ |

Dead-letter: exchange `lead.dlx` (FANOUT) → queue `lead.rejected` (TTL 24h).

---

## Modelo de Dados

### Tabelas principais

```
campanhas
──────────────────────────────────────────────
id                    UUID PK
name                  VARCHAR
slug                  VARCHAR UNIQ
status                VARCHAR (draft|active|paused|finished)
objective             TEXT nullable
source_config         JSONB
offer_description     TEXT nullable       ← novo
ideal_customer_profile TEXT nullable      ← novo
ticket                VARCHAR(100) nullable ← novo
focus_segments        JSONB default []   ← novo
is_active             BOOLEAN
created_at            TIMESTAMPTZ

leads
──────────────────────────────────────────────
id                    UUID PK
name                  VARCHAR
email                 VARCHAR (unique lower idx)
phone                 VARCHAR nullable
company               VARCHAR nullable
source_id             UUID FK → sources
campanha_id           UUID FK → campanhas nullable
niche_id              UUID FK → niches nullable
status                VARCHAR
instagram_username    VARCHAR nullable
instagram_bio         TEXT nullable
instagram_followers   INTEGER nullable
instagram_following   INTEGER nullable
instagram_posts       INTEGER nullable
instagram_engagement_rate FLOAT nullable
instagram_account_type    VARCHAR nullable
instagram_profile_url     VARCHAR nullable
metadata              JSONB
offer_tags            JSONB default []   ← novo
created_at            TIMESTAMPTZ
updated_at            TIMESTAMPTZ (auto-trigger)
```

### offer_tags — estrutura por item

```json
{
  "offer_slug": "bot-prestador",
  "score": 98,
  "channel": "whatsapp",
  "tone": "direto",
  "time": "19h–21h",
  "reason": "MEI ativo, Instagram engajado, serviço de estética",
  "insufficient_data": false
}
```

Um lead acumula uma tag por campanha. Nunca re-analisa a mesma campanha. Histórico fica completo.

### Status do lead (lifecycle — não quebrar a ordem)

```
captured → validated → deduplicated → enriched → scored → distributed
               ↓                                               ↓
           rejected (DLQ)                             contacted → replied → converted
                                                                          ↘ churned
```

---

## Serviços

### Scraper (`services/scraper/`)
- **GooglePlacesSource** (MVP — a implementar): textSearch por termos livres, loop contínua, importação em lote com tag do nicho
- **WebScraperSource**: HTML scraping via httpx + BeautifulSoup
- **ApifyInstagramSource**: perfis públicos via Apify (ativa com `APIFY_TOKEN`)
- Extensível via `SourceRegistry` — `source_name` deve bater com `name` na tabela `sources`

### Validator (`services/validator/`)
- Rejeita: email inválido, domínio descartável, nome vazio
- Lista de descartáveis em `rules/business_rules.py`

### Deduplicator (`services/deduplicator/`)
- Detecta por `LOWER(email)` — merge inteligente (atualiza name, phone, company do existente)

### Enricher (`services/enricher/`)
- **CNPJ.ws** (gratuito, ativo): lookup por CNPJ em `metadata["cnpj"]`
- **Instagram**: re-usa campos do modelo (coletados pelo scraper)
- **BigDataCorp** (stub, requer `BIGDATACORP_TOKEN`)
- **Serasa** (stub, requer `SERASA_CLIENT_ID` + `SERASA_CLIENT_SECRET`)
- Persiste em tabela `enrichments` (1:1 com leads)

### Scorer (`services/scorer/`)
- Score genérico 0–100 por qualidade de dados (Layer 1)
- 5 critérios: data_completeness (30) + source×25 + phone (15) + email_domain (15) + niche×15
- Bônus: Instagram business/creator, followers, engagement, CNPJ ativo, −5 email placeholder
- HOT ≥ 70 / WARM 40–69 / COLD < 40
- Persiste em tabela `scores`

### Orchestrator (`services/orchestrator/`)

**Modo event-driven (existente):** consome `lead.scored`, chama GPT-4o-mini, publica `lead.orchestrated`.
- Campos: `need_identified`, `offer_category`, `approach`, `tone`, `best_time`, `score_adjustment`, `objections[]`, `opening_message`
- Fallback determinístico sem `OPENAI_API_KEY`
- Persiste em `orchestration_decisions`

**Modo varredura (novo):** acionado por `POST /api/campanhas/{id}/analisar`
- Varre leads do banco filtrados por `focus_segments` da campanha
- Para cada lead: verifica se já tem offer_tag para essa campanha (pula se sim)
- GPT recebe: dados do lead + oferta da campanha → retorna nota, canal, tom, horário, motivo
- Salva `offer_tag` no array `leads.offer_tags`
- Pode ser pausado/retomado; erro por lead não quebra a fila

### Distributor (`services/distributor/`)
- Telegram com retry 3x (5s → 15s → 30s)
- HOT/WARM: envia imediatamente; COLD: marca como distribuído sem envio

### Outreach (`services/outreach/`)
- WhatsApp via Evolution API (config required): `EVOLUTION_API_URL` + `EVOLUTION_API_KEY` + `EVOLUTION_INSTANCE`
- Instagram DM: stub (pending_manual)
- Ativar: `OUTREACH_ENABLED=true`

### Feedback (`services/feedback/`)
- Bot Telegram com polling: `/respondeu`, `/convertido`, `/churned`
- Valida transições do lifecycle

### API (`services/api/`)
- `POST /leads` — publica `lead.captured`
- `GET /leads` — lista leads do banco
- `GET /api/overview` — métricas totais
- `GET /api/pipeline` — contagem por status (kanban)
- `GET /api/campanhas` — campanhas ativas
- `POST /api/campanhas/{id}/analisar` — dispara modo varredura (a implementar)
- `GET /api/campanhas/{id}/progresso` — progresso da varredura (a implementar)

---

## Fontes (sources) — multipliers

| name | multiplier | Score máx |
|------|-----------|-----------|
| `paid_traffic` | 1.0 | 25 pts |
| `meta_ads` | 1.0 | 25 pts |
| `google_ads` | 1.0 | 25 pts |
| `google_maps` | 0.9 | 22.5 pts |
| `whatsapp` | 0.8 | 20 pts |
| `instagram` | 0.75 | 18.75 pts |
| `chatbot` | 0.7 | 17.5 pts |
| `csv_import` | 0.6 | 15 pts |
| `web_scraping` | 0.4 | 10 pts |

Alterar no banco tem efeito imediato (cache do scorer é por processo).

---

## Stack

| Componente | Tecnologia |
|-----------|-----------|
| Linguagem | Python 3.11 |
| Mensageria | RabbitMQ (aio-pika) |
| Banco | PostgreSQL 15 (asyncpg) |
| ORM | SQLAlchemy async 2.0 |
| Migrations | Alembic |
| Validação | Pydantic v2 |
| HTTP client | httpx |
| Infraestrutura | Docker Compose |

---

## Variáveis de ambiente críticas

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `RABBITMQ_URL` | `amqp://user:pass@host/` |
| `TELEGRAM_BOT_TOKEN` | Token do bot |
| `TELEGRAM_CHAT_ID` | ID do chat que recebe leads |
| `GOOGLE_PLACES_API_KEY` | Chave Google Places API (Nova Pesquisa) |
| `OPENAI_API_KEY` | Ativa GPT-4o-mini (sem key → fallback determinístico) |
| `ORCHESTRATOR_ENABLED` | Liga/desliga orquestrador event-driven |
| `CNPJWS_ENABLED` | Enriquecimento CNPJ.ws (padrão: true) |
| `EVOLUTION_API_URL` | URL Evolution API (WhatsApp) |
| `EVOLUTION_API_KEY` | API key Evolution |
| `EVOLUTION_INSTANCE` | Instância WhatsApp conectada |
| `OUTREACH_ENABLED` | Habilita envio real (padrão: false) |
| `APIFY_TOKEN` | Ativa coleta Instagram via Apify |

---

## Comandos do dia a dia

```bash
# Subir tudo
cd infra && docker compose up --build -d

# Aplicar migrations (inclui 0002_motor_audiencia)
alembic -c shared/database/migrations/alembic.ini upgrade head

# Logs de um serviço
cd infra && docker compose logs -f orchestrator

# Rebuild de um serviço
cd infra && docker compose up --build -d scraper

# Derrubar tudo + limpar volumes
cd infra && docker compose down -v

# Testes
pytest services/<svc>/tests/
```

---

## MVP Lab — Próximos passos (em ordem)

1. `services/scraper/sources/places.py` — `GooglePlacesSource` com textSearch + loop Liga/Pausa
2. `alembic upgrade head` após `0002_motor_audiencia`
3. `POST /api/campanhas/{id}/analisar` + worker de varredura no orchestrator
4. `GET /api/campanhas/{id}/progresso` com SSE ou polling
5. Dashboard mostra offer_tags no perfil do lead + feed em tempo real

## Débitos conhecidos

| Item | Quando resolver |
|------|----------------|
| Google Places key exposta no HTML | Mover para `GET /api/search` no backend |
| CORS `allow_origins=["*"]` | Restringir ao domínio real em produção |
| Nurture scheduler não executa | Implementar worker com delays configuráveis |
| Instagram DM é stub | Avaliar Facebook Graph API com permissão |
| Custo OpenAI sem budget por campanha | Adicionar `max_tokens_per_campaign` no config |
