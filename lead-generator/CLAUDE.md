# Gerador de Leads — Documentação Técnica

## Visão Geral

Sistema de captação, qualificação e distribuição de leads B2B construído como pipeline
event-driven. Cada estágio é um microserviço Python independente que se comunica
exclusivamente via RabbitMQ. O objetivo final é receber leads de múltiplas fontes,
qualificá-los automaticamente por score e entregar os mais quentes para o time comercial
via Telegram em tempo real.

---

## Arquitetura do Pipeline

```
                        ┌──────────────────────────────────────────────────┐
                        │                  PIPELINE                        │
                        │                                                  │
  Fontes de dados  ──►  │ Scraper ──► Validator ──► Deduplicator           │
  (web, CSV, ads)       │                               │                  │
                        │                            Scorer                │
                        │                               │                  │
                        │                          Distributor ──► Telegram│
                        │                               │                  │
                        │                           Dead-Letter            │
                        └──────────────────────────────────────────────────┘
```

### Fluxo de eventos (routing keys RabbitMQ)

| # | Evento | Publicado por | Consumido por | Descrição |
|---|--------|--------------|---------------|-----------|
| 1 | `lead.captured` | Scraper | Validator | Lead bruto recebido da fonte |
| 2 | `lead.validated` | Validator | Deduplicator | Lead passou nas regras de negócio |
| 3 | `lead.deduplicated` | Deduplicator | Scorer | Lead é novo ou foi mergeado |
| 4 | `lead.scored` | Scorer | Distributor | Lead pontuado com temperatura |
| — | `lead.rejected` | Validator | Dead-letter | Lead inválido descartado |
| — | `lead.dlx` | Distributor | Dead-letter | Falha de entrega após retries |

### Caminhos tristes (sad paths)

| Situação | Comportamento |
|----------|---------------|
| Lead inválido (email/nome) | Validator rejeita → publica `lead.rejected` → DLQ |
| Lead duplicado (mesmo email) | Deduplicator merge dados no lead existente → pipeline continua com ID original |
| Lead COLD (score < 40) | Distributor marca como distribuído e salva para recontato — sem Telegram imediato |
| Falha no Telegram | Distributor retenta 3x (delays: 5s, 15s, 30s) → DLQ após esgotar |

---

## Stack Tecnológica

| Componente | Tecnologia | Versão |
|------------|-----------|--------|
| Linguagem | Python | 3.11 |
| Mensageria | RabbitMQ (aio-pika) | 3.12 / 9.4 |
| Banco de dados | PostgreSQL (asyncpg) | 15 / 0.29 |
| ORM | SQLAlchemy async | 2.0.30 |
| Migrations | Alembic | 1.13 |
| Validação de modelos | Pydantic v2 | 2.7.1 |
| Logging estruturado | structlog | 24.2 |
| HTTP client | httpx | 0.27 |
| Infraestrutura | Docker Compose | — |
| Interface DB | pgAdmin 4 | latest |

### Decisões arquiteturais

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| Mensageria | RabbitMQ TOPIC exchange | Múltiplos consumers por evento sem alterar producers |
| Deduplicação | Unique index `LOWER(email)` | Idempotência garantida pelo banco sem coordenação distribuída |
| Dead-letter | Exchange FANOUT `lead.dlx` | Centraliza falhas sem acoplamento entre serviços |
| Source como entidade | Tabela `sources` com FK | Multiplier de score configurável por banco, sem redeploy |
| Score | Pesos configuráveis via env | Ajuste de threshold sem alteração de código |

---

## Modelo de Dados

### Diagrama de tabelas

```
niches                    sources                    leads
──────────────────        ───────────────────────    ──────────────────────────
id          UUID PK       id          UUID PK        id          UUID PK
name        VARCHAR UNIQ  name        VARCHAR UNIQ   name        VARCHAR
slug        VARCHAR UNIQ  label       VARCHAR        email       VARCHAR (idx unique lower)
description TEXT          channel     VARCHAR        phone       VARCHAR nullable
is_active   BOOLEAN       base_score_multiplier FLOAT company    VARCHAR nullable
created_at  TIMESTAMPTZ   is_active   BOOLEAN        source_id   UUID FK → sources
                          created_at  TIMESTAMPTZ    niche_id    UUID FK → niches nullable
                                                     status      VARCHAR
                                                     metadata    JSONB
                                                     created_at  TIMESTAMPTZ
                                                     updated_at  TIMESTAMPTZ (auto-trigger)

scores
──────────────────────
id          SERIAL PK
lead_id     UUID FK → leads (cascade delete)
score       FLOAT
temperature VARCHAR (HOT|WARM|COLD)
breakdown   JSONB
scored_at   TIMESTAMPTZ
notes       TEXT nullable
```

### Status do lead (ciclo de vida)

```
captured → validated → deduplicated → scored → distributed
                ↓
            rejected (DLQ)
```

---

## Serviços

### Scraper
- Ciclo periódico configurável via `SCRAPER_INTERVAL_SECONDS`
- Resolve `source_id` no banco antes de publicar (falha graciosamente se fonte não cadastrada)
- Extensível via `SourceRegistry` — novas fontes não exigem alteração no `main.py`
- Fonte atual implementada: `WebScraperSource` (HTML scraping via httpx + BeautifulSoup)

### Validator
- Rejeita leads com email inválido, email descartável (mailinator, tempmail, etc.) ou nome vazio
- Lista de domínios descartáveis em `services/validator/rules/business_rules.py`

### Deduplicator
- Detecta duplicatas por `LOWER(email)` comparando com todos os leads existentes
- Em caso de duplicata: atualiza `name`, `phone`, `company`, `source_id` do lead existente e continua o pipeline com o ID original
- Em caso de lead novo: insere no banco e avança

### Scorer
- Score 0–100 composto por 4 critérios (pesos configuráveis via env)
- Persiste resultado em `scores` e atualiza status do lead
- Cache em memória para `base_score_multiplier` por fonte (evita query a cada lead)

#### Critérios de score

| Critério | Peso padrão | Lógica |
|----------|-------------|--------|
| `data_completeness` | 40 pts | name+email obrigatórios (60%), phone+company opcionais (40%) |
| `source` | 25 pts | `base_score_multiplier` da tabela `sources` × 25 |
| `phone_present` | 20 pts | telefone preenchido = 100% |
| `email_domain` | 15 pts | corporativo=100%, trusted(gmail/outlook)=60%, outros=30% |

#### Temperaturas

| Temperatura | Faixa | Comportamento |
|-------------|-------|---------------|
| HOT | ≥ 70 | Enviado imediatamente ao Telegram |
| WARM | 40–69 | Enviado imediatamente ao Telegram |
| COLD | < 40 | Salvo para recontato futuro, sem envio imediato |

### Distributor
- Canal atual: Telegram (mensagem formatada com emoji por temperatura)
- Retry automático: 3 tentativas com backoff (5s → 15s → 30s)
- COLD leads: marcados como distribuídos sem envio
- Falha total: publica payload no DLQ com motivo

---

## Tabela de Fontes (sources)

O campo `base_score_multiplier` determina o peso desta fonte no score final.
Alterar no banco tem efeito imediato (cache do scorer é por processo).

| name | label | channel | multiplier | Score máximo da fonte |
|------|-------|---------|------------|----------------------|
| `paid_traffic` | Tráfego Pago | paid | 1.0 | 25 pts |
| `meta_ads` | Meta Ads | paid | 1.0 | 25 pts |
| `google_ads` | Google Ads | paid | 1.0 | 25 pts |
| `whatsapp` | WhatsApp | direct | 0.8 | 20 pts |
| `chatbot` | Chatbot | direct | 0.7 | 17.5 pts |
| `csv_import` | Importação CSV | manual | 0.6 | 15 pts |
| `web_scraping` | Web Scraping | organic | 0.4 | 10 pts |

---

## Como Estender o Sistema

### Adicionar nova fonte de leads

1. Inserir linha na tabela `sources` — `name` único, `base_score_multiplier` entre 0.0 e 1.0
2. Criar `services/scraper/sources/minha_fonte.py` implementando `BaseSource`
   - `source_name` deve retornar exatamente o `name` inserido no banco
   - `fetch()` deve retornar `list[RawLead]`
3. Registrar em `build_registry()` em [services/scraper/main.py](services/scraper/main.py)
4. Nenhuma alteração nos outros workers

### Adicionar novo canal de distribuição

1. Criar `services/distributor/channels/meu_canal.py` implementando `async send(lead, score, temperature) -> bool`
2. Instanciar em `main()` de [services/distributor/main.py](services/distributor/main.py)
3. Chamar `await meu_canal.send(...)` em `handle_lead_scored()`
4. Adicionar credenciais em `.env.example` e `shared/config.py`

---

## Comandos do Dia a Dia

```bash
# Subir toda a stack (rebuild completo)
cd infra && docker compose up --build -d

# Ver logs de um worker específico
cd infra && docker compose logs -f scorer

# Derrubar tudo e limpar volumes (reset total)
cd infra && docker compose down -v

# Rebuild de um serviço específico
cd infra && docker compose up --build -d scraper

# Rodar apenas a infra (postgres + rabbitmq + pgadmin)
cd infra && docker compose up -d postgres rabbitmq pgadmin

# Criar nova migration Alembic
alembic -c shared/database/migrations/alembic.ini revision --autogenerate -m "descricao"

# Aplicar migrations pendentes
alembic -c shared/database/migrations/alembic.ini upgrade head

# Interfaces web
# pgAdmin  → http://localhost:5050   (admin@admin.com / admin)
# RabbitMQ → http://localhost:15672  (guest / guest)

# Publicar lead de teste (buscar source_id no pgAdmin primeiro)
docker exec lead-validator python -c "
import asyncio
from shared.broker.rabbitmq import RabbitMQPublisher
from shared.models.events import LeadCapturedEvent
from shared.models.lead import Lead
from uuid import UUID

async def main():
    pub = RabbitMQPublisher('amqp://guest:guest@rabbitmq:5672/')
    await pub.connect()
    lead = Lead(
        name='João Silva',
        email='joao@empresa.com.br',
        phone='+5511999990000',
        source_id=UUID('SEU-SOURCE-ID-AQUI'),
        source_name='paid_traffic',
    )
    event = LeadCapturedEvent(lead=lead)
    await pub.publish('lead.captured', event.model_dump(mode='json'))
    print('Lead publicado:', lead.id)
    await pub.close()

asyncio.run(main())
"
```

---

## Variáveis de Ambiente Críticas

Ver [.env.example](.env.example) para lista completa.

| Variável | Descrição |
|----------|-----------|
| `RABBITMQ_URL` | URL de conexão RabbitMQ (`amqp://user:pass@host/`) |
| `DATABASE_URL` | URL async PostgreSQL (`postgresql+asyncpg://...`) |
| `TELEGRAM_BOT_TOKEN` | Token do bot do Telegram |
| `TELEGRAM_CHAT_ID` | ID do chat/grupo que recebe os leads |
| `SCRAPER_TARGET_URLS` | URLs separadas por vírgula para scraping |
| `SCRAPER_INTERVAL_SECONDS` | Intervalo entre ciclos do scraper (padrão: 300s) |
| `HOT_SCORE_THRESHOLD` | Score mínimo para HOT (padrão: 70) |
| `WARM_SCORE_THRESHOLD` | Score mínimo para WARM (padrão: 40) |
| `SCORE_WEIGHT_DATA_COMPLETENESS` | Peso completude (padrão: 40) |
| `SCORE_WEIGHT_SOURCE` | Peso fonte (padrão: 25) |
| `SCORE_WEIGHT_PHONE_PRESENT` | Peso telefone (padrão: 20) |
| `SCORE_WEIGHT_EMAIL_DOMAIN` | Peso domínio email (padrão: 15) |

---

## Projeção de MVP

### Estado atual (base funcional)

O pipeline está operacional end-to-end com todas as regras de negócio implementadas.
O que existe hoje é suficiente para processar leads reais — falta apenas conectar fontes
de dados reais e validar os pesos de score com dados concretos.

```
✅ Pipeline completo (scraper → validator → deduplicator → scorer → distributor)
✅ Entrega via Telegram com retry
✅ Deduplicação com merge de dados
✅ Score configurável com temperatura HOT/WARM/COLD
✅ Source como entidade com multiplier no banco
✅ Dead-letter queue para falhas
✅ pgAdmin para visualização do banco
✅ Infraestrutura Docker Compose completa
```

---

### MVP — Definição

> Primeiro lead real de uma campanha paga chegando no Telegram com score correto,
> sem intervenção manual.

---

### Roadmap por fase

#### Fase 1 — Primeira fonte real (1–2 semanas)

Objetivo: ingerir leads reais sem depender de scraping genérico.

| Tarefa | Descrição | Prioridade |
|--------|-----------|------------|
| Importador CSV | Worker `csv_importer` que lê arquivo, normaliza e publica `lead.captured` | Alta |
| Mapeamento de campos | Suporte a diferentes formatos de CSV (header mapping configurável) | Alta |
| Validação de dados históricos | Rodar leads antigos pelo pipeline e observar distribuição de scores | Alta |
| Ajuste de pesos | Calibrar `base_score_multiplier` e pesos do scorer com base nos resultados reais | Média |

**Entregável:** conseguir rodar uma campanha CSV antiga e ver os leads chegando no Telegram classificados corretamente.

---

#### Fase 2 — Integração com tráfego pago (2–4 semanas)

Objetivo: receber leads de Meta Ads ou Google Ads em tempo real via webhook.

| Tarefa | Descrição | Prioridade |
|--------|-----------|------------|
| API de entrada (FastAPI) | Endpoint `POST /leads/ingest` que recebe webhook e publica `lead.captured` | Alta |
| Autenticação do webhook | Verificação de assinatura HMAC para Meta/Google | Alta |
| Integração Meta Ads Lead Forms | Configurar webhook no Meta Business Manager | Alta |
| Mapeamento de campos do Meta | Normalizar campos do formulário para modelo `Lead` | Alta |
| Testes de carga básico | Garantir que o pipeline suporta burst de leads de uma campanha ativa | Média |

**Entregável:** campanha ativa no Meta Ads entregando leads direto no Telegram sem intervenção.

---

#### Fase 3 — Qualidade e observabilidade (2–3 semanas)

Objetivo: entender o que está acontecendo e melhorar a qualidade dos leads entregues.

| Tarefa | Descrição | Prioridade |
|--------|-----------|------------|
| Dashboard de métricas | Painel no pgAdmin ou Grafana com volume por fonte, distribuição de temperatura, taxa de rejeição | Alta |
| Score com contexto de mercado | Enriquecer score com segmento da empresa (niche_id) — leads de nicho-alvo valem mais | Média |
| Recontato COLD | Worker `recontact_scheduler` que reprocessa leads COLD em cadência definida | Média |
| Alertas de DLQ | Notificação no Telegram quando mensagens entram no dead-letter | Média |
| Monitoramento de fontes | Alerta quando uma fonte para de entregar leads (ausência > X horas) | Baixa |

**Entregável:** conseguir responder "quantos leads HOT chegaram hoje e de qual fonte".

---

#### Fase 4 — Score inteligente (4–6 semanas)

Objetivo: qualificação contextual usando dados de mercado e histórico de conversão.

| Tarefa | Descrição | Prioridade |
|--------|-----------|------------|
| Score por conversão histórica | Registrar quais leads viraram clientes e usar para calibrar pesos automaticamente | Alta |
| Enriquecimento com IA | Chamar API do Claude com perfil do lead para score contextual (cargo, segmento, empresa) | Média |
| Score por nicho | Multiplier adicional baseado na aderência do lead ao nicho-alvo do cliente | Média |
| A/B de pesos | Testar diferentes configurações de peso em paralelo e medir resultado | Baixa |

**Entregável:** taxa de conversão de leads HOT mensurável e em melhoria contínua.

---

### Critérios de sucesso do MVP (Fase 1 + 2)

| Métrica | Meta |
|---------|------|
| Tempo do lead (captura → Telegram) | < 5 segundos |
| Taxa de rejeição | < 15% dos leads capturados |
| Leads HOT entregues por campanha | ≥ 30% do total capturado |
| Uptime do pipeline | > 99% durante campanha ativa |
| Zero intervenção manual | Nenhum lead precisa ser encaminhado manualmente |

---

### Débitos técnicos conhecidos

| Item | Impacto | Quando resolver |
|------|---------|-----------------|
| `SOURCE_LABEL` hardcoded no `telegram.py` | Telegram exibe nome errado para fontes novas | Fase 2 — ler `source_name` direto do payload |
| Cache de `source_multiplier` por processo | Alteração no banco não reflete sem restart do scorer | Fase 3 — TTL de cache ou invalidação via evento |
| Sem testes automatizados | Regressions não detectadas antes do deploy | Fase 2 — testes unitários no scorer e validator |
| Alembic migration manual | Migration `a1b2c3d4e5f6` foi escrita à mão | Já funcional, mas gerar via autogenerate na próxima |
