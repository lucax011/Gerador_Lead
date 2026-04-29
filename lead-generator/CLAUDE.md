# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão Geral

Plataforma B2B que refina potenciais clientes de qualquer nicho para uma oferta específica. O operador busca leads via Google Places, enriquece com CNPJ.ws e Instagram, executa o orquestrador IA contra uma oferta definida, e o banco de leads sai com `offer_tags` prontos para o bot de abordagem consumir.

**Princípio central:** score não é do lead — é da relação lead × oferta. Um lead pode ter 98 pts para "bot de automação MEI" e 40 pts para "consórcio R$ 200k".

---

## Comandos do dia a dia

```bash
# Subir tudo
cd infra && docker compose up --build -d

# Rebuild de um serviço específico
cd infra && docker compose up --build -d scraper

# Logs de um serviço
cd infra && docker compose logs -f orchestrator

# Derrubar tudo + limpar volumes
cd infra && docker compose down -v

# Aplicar migrations
alembic -c shared/database/migrations/alembic.ini upgrade head

# Criar nova migration
alembic -c shared/database/migrations/alembic.ini revision -m "descricao"

# Rodar todos os testes
pytest

# Rodar testes de um serviço
pytest services/scorer/tests/
pytest tests/api/

# Rodar um teste específico
pytest tests/scorer/test_scoring_engine.py::test_hot_lead -v
```

---

## Arquitetura

```
  Dashboard Web → http://localhost:8000
         │
         │  POST /leads   GET /leads   GET /api/*
         │  POST /api/campanhas/{id}/analisar  ← modo varredura (roda dentro da API)
         ▼
  ┌──────────────────────────────────────────────────────────┐
  │  API FastAPI  (services/api/main.py)                     │
  │  · Serve static/index.html                               │
  │  · Publica lead.captured → RabbitMQ                      │
  │  · Executa modo varredura internamente (_run_sweep)       │
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

## Padrão de Worker

Todo serviço (exceto API) segue este padrão:

```python
async def main():
    settings = get_settings()
    publisher = RabbitMQPublisher(settings.RABBITMQ_URL)
    consumer = RabbitMQConsumer(settings.RABBITMQ_URL)
    await publisher.connect()

    async def handle(payload: dict):
        event = LeadXxxEvent(**payload)
        async with AsyncSessionLocal() as session:
            # lógica de negócio
            await publisher.publish("lead.next_stage", NextEvent(...))

    await consumer.consume("queue-name", "lead.current_stage", handle)

if __name__ == "__main__":
    asyncio.run(main())
```

- Erros não tratados → dead-letter via `publisher.publish_to_dead_letter(payload, reason)`
- QoS prefetch_count=10 (configurado no consumer)
- Logs com `structlog`; nunca `print()`
- Config via `get_settings()` (LRU cache) — nunca `os.environ` direto

---

## Modo Varredura — onde vive

**Importante:** o modo varredura **não é um worker separado** — roda dentro de `services/api/main.py`.

- `POST /api/campanhas/{id}/analisar` → cria entrada em `sweep_jobs: dict[str, dict]` (in-memory, perdido ao reiniciar a API)
- `asyncio.create_task(_run_sweep(...))` executa em background dentro do processo da API
- `GET /api/campanhas/{id}/progresso` → polling do estado em `sweep_jobs`
- `POST /api/jobs/{job_id}/pausar|retomar` → altera flag no dict

Fluxo interno de `_run_sweep`:
1. Carrega campanha e leads filtrados por `focus_segments`
2. Pula leads que já têm `offer_tag` para essa campanha (slug = `campanha.slug`)
3. Chama `_call_openai_sweep()` → GPT-4o-mini com `SWEEP_PROMPT`
4. Fallback determinístico `_fallback_sweep()` se `OPENAI_API_KEY` ausente
5. Faz append em `lead.offer_tags` (JSONB array) via UPDATE no banco

---

## Modelo de Dados

### Tabelas principais (ORM em `shared/database/models.py`)

```
campanhas: id, name, slug (unique), status, source_config (JSONB),
           offer_description, ideal_customer_profile, ticket, focus_segments (JSONB [])

leads: id, name, email (unique lower idx), phone, company,
       source_id (FK), campanha_id (FK), niche_id (FK), status,
       instagram_username, instagram_bio, instagram_followers,
       instagram_following, instagram_posts, instagram_engagement_rate,
       instagram_account_type, instagram_profile_url,
       metadata_ (JSONB), offer_tags (JSONB [])

scores: id, lead_id, score (float), temperature, breakdown (JSONB)
enrichments: id, lead_id (unique), cnpj_data, instagram_data, ... (JSONB)
orchestration_decisions: id, lead_id, approach, tone, opening_message, ...
outreach_attempts: id, lead_id, channel, status, scheduled_at, sent_at
niches: id, name (unique), niche_score_multiplier
sources: id, name (unique), base_score_multiplier
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

Um lead acumula uma tag por campanha. Nunca re-analisa a mesma campanha. `offer_tags` nunca substitui `score` genérico — são layers independentes.

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
- **GooglePlacesSource** (a implementar em `sources/places.py`): textSearch por termos livres, loop contínua, importação em lote com tag do nicho
- **WebScraperSource**: HTML scraping via httpx + BeautifulSoup
- **ApifyInstagramSource**: ativa com `APIFY_TOKEN`
- Extensível via `SourceRegistry` — `source_name` deve bater com `name` na tabela `sources`

### Validator (`services/validator/`)
- Rejeita: email inválido, domínio descartável, nome vazio
- Lista de domínios descartáveis em `rules/business_rules.py`

### Deduplicator (`services/deduplicator/`)
- Detecta por `LOWER(email)` — merge inteligente (atualiza name, phone, company do existente se o novo tiver)

### Enricher (`services/enricher/`)
- **CNPJ.ws** (gratuito, ativo por padrão): lookup por CNPJ em `metadata["cnpj"]`
- **BigDataCorp** e **Serasa**: stubs (requerem tokens)
- Persiste em `enrichments` (1:1 com leads)

### Scorer (`services/scorer/`)
- Layer 1 — qualidade de dados (0–100):
  - `data_completeness` ×30 + `source.base_score_multiplier` ×25 + `phone` ×15 + `email_domain` ×15 + `niche.niche_score_multiplier` ×15
  - Bônus Instagram: business +5/creator +3; followers 10k+ +8/1k+ +4/500+ +2; engagement 5%+ +5/3%+ +3
  - Bônus CNPJ ativo +5; penalidade email placeholder −5
- HOT ≥ 70 / WARM 40–69 / COLD < 40
- Multipliers vêm do banco (sem cache entre restarts); fallback niche = 0.5

### Orchestrator (`services/orchestrator/`)
- **Event-driven:** consome `lead.scored`, chama GPT-4o-mini, publica `lead.orchestrated`
- `NICHE_CONTEXTS` dict no código: 15 nichos com instruções customizadas para o GPT (ex: `beleza-estetica`, `imoveis`)
- Campos de saída: `need_identified`, `approach` (whatsapp/instagram_dm/nurture/none), `tone`, `best_time`, `opening_message`
- Fallback determinístico: COLD → nurture; HOT + Instagram → instagram_dm; HOT + telefone → whatsapp

### Distributor (`services/distributor/`)
- Telegram com retry 3× (5s → 15s → 30s)
- HOT/WARM: envia imediatamente; COLD: marca distribuído sem envio

### Outreach (`services/outreach/`)
- WhatsApp via Evolution API: `EVOLUTION_API_URL` + `EVOLUTION_API_KEY` + `EVOLUTION_INSTANCE`
- Instagram DM: stub
- Ativar: `OUTREACH_ENABLED=true`

### Feedback (`services/feedback/`)
- Bot Telegram polling: `/respondeu`, `/convertido`, `/churned`
- Valida transições do lifecycle

### API (`services/api/`)

| Método | Rota | Função |
|--------|------|--------|
| POST | `/leads` | Publica `lead.captured` |
| POST | `/leads/csv` | Importação em lote com field aliasing |
| GET | `/leads` | Lista leads com score e estágio (limit=200) |
| PATCH | `/leads/{id}/stage` | Update manual de status |
| GET | `/api/overview` | Métricas totais |
| GET | `/api/pipeline` | Contagem por status (kanban) |
| GET | `/api/pipeline/scores` | Distribuição de scores |
| GET | `/api/campanhas` | Lista campanhas ativas |
| POST | `/api/campanhas/{id}/analisar` | Dispara modo varredura (202 Accepted) |
| GET | `/api/campanhas/{id}/progresso` | Polling do progresso |
| POST | `/api/jobs/{id}/pausar` | Pausa varredura |
| POST | `/api/jobs/{id}/retomar` | Retoma varredura |
| GET | `/api/leads/{id}/orchestration` | Decisão do orquestrador para o lead |
| POST | `/api/leads/{id}/telegram` | Envia mensagem de teste no Telegram |

`ORIGIN_TO_SOURCE` no `main.py` mapeia origem do frontend para `name` na tabela `sources` (ex: `"maps"` → `"google_maps"`).

---

## Fontes (sources) — multipliers

| name | multiplier |
|------|-----------|
| `paid_traffic`, `meta_ads`, `google_ads` | 1.0 |
| `google_maps` | 0.9 |
| `whatsapp` | 0.8 |
| `instagram` | 0.75 |
| `chatbot` | 0.7 |
| `csv_import` | 0.6 |
| `web_scraping` | 0.4 |

Alterar no banco tem efeito imediato (sem cache entre processos).

---

## Variáveis de ambiente críticas

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `RABBITMQ_URL` | `amqp://user:pass@host/` |
| `TELEGRAM_BOT_TOKEN` | Token do bot |
| `TELEGRAM_CHAT_ID` | ID do chat que recebe leads |
| `GOOGLE_PLACES_API_KEY` | Chave Google Places API |
| `OPENAI_API_KEY` | Ativa GPT-4o-mini (sem key → fallback determinístico) |
| `ORCHESTRATOR_ENABLED` | Liga/desliga orquestrador event-driven |
| `CNPJWS_ENABLED` | Enriquecimento CNPJ.ws (padrão: true) |
| `EVOLUTION_API_URL` / `EVOLUTION_API_KEY` / `EVOLUTION_INSTANCE` | WhatsApp |
| `OUTREACH_ENABLED` | Habilita envio real (padrão: false) |
| `APIFY_TOKEN` | Ativa coleta Instagram via Apify |

---

## MVP Lab — Próximos passos (em ordem)

1. `services/scraper/sources/places.py` — `GooglePlacesSource` com textSearch + loop Liga/Pausa
2. Dashboard mostra `offer_tags` no perfil do lead + feed de progresso da varredura em tempo real

## Débitos conhecidos

| Item | Quando resolver |
|------|----------------|
| `sweep_jobs` in-memory | Persistir em Redis ou tabela para sobreviver a restart da API |
| Google Places key exposta no HTML | Mover para `GET /api/search` no backend |
| CORS `allow_origins=["*"]` | Restringir ao domínio real em produção |
| Nurture scheduler não executa | Implementar worker com delays configuráveis |
| Instagram DM é stub | Avaliar Facebook Graph API com permissão |
| Custo OpenAI sem budget por campanha | Adicionar `max_tokens_per_campaign` no config |
