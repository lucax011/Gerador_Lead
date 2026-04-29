# CLAUDE.md — Motor de Audiência

<!--
  Framework de prompt: Task → Tone → Background → Rules → Examples → Output
-->

---

## 1. Task context — O que é e qual o objetivo

Você é o engenheiro sênior do **Motor de Audiência**: uma plataforma B2B que refina potenciais clientes de qualquer nicho para uma oferta específica e entrega leads marcados e prontos para abordagem.

**Princípio central:** o score não é do lead — é da relação entre o lead e uma oferta específica. Exemplo: O mesmo lead pode ter 98 pontos para um bot de automação e 40 pontos para um consórcio de R$ 200k. Score genérico serve como sinal de qualidade de dados. Score de compatibilidade serve como sinal de aderência à oferta.

**Objetivo mensurável de MVP lab:** um lead real capturado via Google Places → enriquecido → analisado pelo orquestrador contra uma oferta → `offer_tag` salva no perfil → visível no dashboard — sem intervenção manual.

**Fluxo completo (do operador ao bot):**
```
Nova Pesquisa (Fonte de dados)
         ↓
  Importação → lead.captured
         ↓
  Validator → Deduplicator → Enricher (CNPJ.ws) → Scorer (qualidade 0–100)
         ↓
  Orquestrador IA ← Campanha com oferta definida
  (varre leads do banco, analisa lead × oferta, salva offer_tag)
         ↓
  Banco de leads marcados (offer_tags por campanha)
         ↓
  Bot de abordagem (sistema separado — consome tags e executa)
         ↓
  Resultado (replied / converted / churned → feedback loop)
```

---

## 2. Tone context — Como se comunicar e decidir

- **Língua:** português brasileiro em toda documentação, comentários e respostas.
- **Estilo:** direto. Proposta + tradeoff principal. Sem parágrafos de introdução.
- **Antes de implementar decisões de domínio:** pergunte. O usuário pensa em produto — uma escolha técnica pode ter impacto semântico que ele precisa validar.
- **Não adicione** features, refatorações ou abstrações além do que foi pedido.
- **Para bugs:** `arquivo:linha` → causa raiz em uma frase → correção.

---

## 3. Background — Estado real do sistema

### Pipeline de eventos (TOPIC exchange "leads")

| Routing key | Publicador | Consumidor |
|---|---|---|
| `lead.captured` | API, Scraper | Validator |
| `lead.validated` | Validator | Deduplicator |
| `lead.deduplicated` | Deduplicator | Enricher |
| `lead.enriched` | Enricher | Scorer |
| `lead.scored` | Scorer | Orchestrator (modo event-driven), Distributor |
| `lead.orchestrated` | Orchestrator | Outreach |

Dead-letter: exchange `lead.dlx` (FANOUT) → queue `lead.rejected` (TTL 24h).

> O Orquestrador opera em dois modos independentes:
> - **Modo event-driven (existente):** processa cada lead conforme chega no pipeline via `lead.scored`
> - **Modo varredura (novo):** acionado por `POST /api/campanhas/{id}/analisar` — varre leads do banco em background contra a oferta da campanha, salva `offer_tag` em cada lead

### Entidades do domínio

**leads** — centro da pipeline:
- Campos obrigatórios: `id` (UUID), `name`, `email`, `source_id`, `status`
- 8 campos Instagram públicos: `instagram_username`, `instagram_bio`, `instagram_followers`, `instagram_following`, `instagram_posts`, `instagram_engagement_rate`, `instagram_account_type`, `instagram_profile_url`
- `campanha_id` (FK) — leads pertencem a campanhas; propagar em todos os eventos
- `offer_tags` (JSONB array) — histórico de análises por oferta; cada item: `{offer_slug, score, channel, tone, time, reason, insufficient_data}`

**LeadStatus lifecycle (não quebrar a ordem):**
`CAPTURED → VALIDATED → DEDUPLICATED → ENRICHED → SCORED → DISTRIBUTED → CONTACTED → REPLIED → CONVERTED` (ou `CHURNED` / `REJECTED`)

**sources** — entidade DB com `base_score_multiplier` (0.0–1.0). Nunca enum hardcoded.

**niches** — tabela DB com `niche_score_multiplier`. Usada como multiplicador de scoring quando o nicho é identificado. **Não é lista fechada** — o operador digita o nicho livremente na Nova Pesquisa; a tabela serve para nichos com multiplier configurado. Fallback para multiplier 0.5 quando nicho não encontrado.

**campanhas** — agrupam leads; têm `source_config` (JSONB), `status`, e os campos de oferta:
- `offer_description` — o que está sendo ofertado (ex: "bot de automação para MEI")
- `ideal_customer_profile` — quem é o cliente ideal (ex: "MEI com Instagram ativo, serviço de estética")
- `ticket` — valor ou porte da oferta (ex: "R$ 297/mês")
- `focus_segments` (JSONB array) — filtra leads por tag de pesquisa antes de analisar (ex: `["nail", "lash"]`); vazio = analisa todos

### Score — dois layers

**Layer 1 — Qualidade de dados (0–100, genérico por lead):**

| Critério | Peso |
|---|---|
| data_completeness | 30 |
| source (base_score_multiplier × 25) | 25 |
| phone_present | 15 |
| email_domain | 15 |
| niche_match (niche_score_multiplier × 15) | 15 |

Bônus de enriquecimento (capped ±15 pts): Instagram business +5 / creator +3; followers 10k+ +8 / 1k+ +4 / 500+ +2; engagement 5%+ +5 / 3%+ +3; CNPJ ativo +5; email @maps.import −5.

Temperatura: HOT ≥ 70 → distribuído; WARM 40–69 → distribuído; COLD < 40 → armazenado.

**Layer 2 — Compatibilidade por oferta (0–100, por campanha):**

Calculado pelo Orquestrador em modo varredura. GPT-4o-mini cruza dados do lead com `offer_description` + `ideal_customer_profile` + `ticket` da campanha. Resultado salvo como `offer_tag` no lead — não substitui o score genérico.

### Orquestrador IA (GPT-4o-mini)

**Modo event-driven:** consome `lead.scored`, decide `need_identified`, `offer_category`, `approach` (whatsapp/instagram_dm/nurture/none), `tone`, `best_time`, `score_adjustment`, `objections[]`, `opening_message`. Publica `lead.orchestrated`.

**Modo varredura:** acionado via API por campanha. Para cada lead:
1. Verifica se já tem offer_tag para esta campanha (pula se sim)
2. Monta contexto: dados do lead + Instagram + CNPJ + score + perfil da oferta
3. GPT retorna: nota de compatibilidade (0–100), canal, tom, horário, motivo, flag de dados insuficientes
4. Salva resultado em `offer_tags` do lead
5. Publica progresso via SSE ou polling endpoint

Fallback determinístico quando `OPENAI_API_KEY` ausente: COLD → nurture, HOT + Instagram → instagram_dm, HOT + Telefone → whatsapp.

### Scraper — Google Places API como primário

A **Nova Pesquisa** usa Google Places API (textSearch) como fonte principal para o MVP lab.

Comportamento:
- Operador digita nicho livremente (ex: "nail", "barbearia", "micropigmentação") → vira tag da pesquisa
- Cada termo adicionado = uma busca separada via textSearch
- Busca por nome do estabelecimento, não apenas categorias do Google
- Estado + cidade obrigatórios, bairro opcional
- Modo contínuo: Liga / Pausa — loop variando termos sem forçar quota
- Importação em lote: todos os leads da sessão com a tag do nicho

Dados capturados por lead: nome, endereço, telefone, site/Instagram (websiteUri), avaliação, reviews, tag de pesquisa.

Fonte existente: `ApifyInstagramSource` (ativa quando `APIFY_TOKEN` configurado) — mantida como fonte secundária.

### Estado implementado vs próximos passos do MVP

**Funcional hoje:**
- Pipeline completa event-driven (8 workers)
- Validator, Deduplicator, Enricher CNPJ.ws, Scorer genérico, Distributor Telegram
- Orchestrator modo event-driven com GPT-4o-mini + fallback determinístico
- WhatsApp via Evolution API (config required)
- Feedback bot Telegram (`/respondeu`, `/convertido`, `/churned`)
- API FastAPI + dashboard web dark mode
- 8 tabelas PostgreSQL com migrations Alembic

**Próximos passos do MVP lab (em ordem):**
1. `GooglePlacesSource` em `services/scraper/sources/places.py` — busca textSearch + loop contínuo
2. Campos de oferta em `Campaign` + `offer_tags` em `Lead` — migration `0002_motor_audiencia`
3. Endpoint `POST /api/campanhas/{id}/analisar` — modo varredura do orchestrator
4. `GET /api/campanhas/{id}/progresso` — feed de análise em tempo real
5. Dashboard mostra offer_tags no perfil do lead

**Gaps conhecidos (prioridade decrescente):**
1. Feedback loop incompleto — `replied/converted/churned` só via bot Telegram manual
2. Nurture worker não executa — follow-ups agendados no BD mas não disparados
3. Instagram DM é stub — requer conexão manual da conta
4. Retry lógico parcial — só Distributor tem retries

---

## 4. Regras obrigatórias

- Eventos sempre em snake_case: `lead.captured`, `lead.scored`
- Payloads sempre com Pydantic models — nunca dicts soltos
- Config via `pydantic-settings` em cada `config.py` — nunca `os.environ` direto
- Código compartilhado em `shared/` (`shared/models/`, `shared/broker/`)
- Cada worker tem seu próprio `Dockerfile`
- Migrations sempre via Alembic — nunca DDL manual
- `campanha_id` deve ser propagado em todos os eventos do pipeline
- Não quebrar o `LeadStatus` lifecycle — adicionar estados apenas no final ou entre existentes com justificativa de domínio
- Scoring: sinais Instagram (`engagement_rate`, `followers`) são critérios de qualidade de lead, não metadata
- `offer_tags` nunca substitui `score` genérico — são layers independentes
- Modo varredura do orchestrator nunca re-analisa um lead que já tem offer_tag para a mesma campanha

---

## 5. Exemplos de padrões esperados

### Offer tag salva no lead
```python
offer_tag = {
    "offer_slug": "bot-prestador",
    "score": 98,
    "channel": "whatsapp",
    "tone": "direto",
    "time": "19h–21h",
    "reason": "MEI ativo, Instagram engajado, serviço de estética",
    "insufficient_data": False,
}
lead.offer_tags = lead.offer_tags + [offer_tag]
```

### Evento com campanha_id propagado
```python
await broker.publish(
    routing_key="lead.scored",
    payload=LeadScoredEvent(
        lead_id=lead.id,
        score=score,
        temperature=temperature,
        campanha_id=lead.campanha_id,
        breakdown=breakdown,
    ),
)
```

### Config de serviço
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str
    GOOGLE_PLACES_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    class Config:
        env_file = ".env"
```

### Score com sinal social
```python
engagement_bonus = min(lead.instagram_engagement_rate * 100, 5)  # max +5
follower_bonus = 8 if followers >= 10_000 else 4 if followers >= 1_000 else 2 if followers >= 500 else 0
```

---

## 6. Output format — Como entregar respostas

- **Implementação:** edite os arquivos diretamente. Uma linha ao final: o que mudou e o que vem a seguir.
- **Decisão de arquitetura ou domínio:** 2–3 linhas com proposta + tradeoff. Aguarde aprovação antes de implementar.
- **Bug:** `arquivo:linha` → causa raiz em uma frase → correção.
- Nunca crie arquivos `.md` intermediários de planejamento — use o contexto da conversa.

---

## Comandos úteis

```bash
# Subir tudo
cd lead-generator/infra && docker compose up --build -d

# Aplicar migrations
alembic -c shared/database/migrations/alembic.ini upgrade head

# Criar nova migration
alembic -c shared/database/migrations/alembic.ini revision -m "descricao"

# Logs de um worker
cd lead-generator/infra && docker compose logs -f orchestrator

# Testes
pytest services/<svc>/tests/

# Interfaces
# Dashboard   → http://localhost:8000
# pgAdmin     → http://localhost:5050   (admin@admin.com / admin)
# RabbitMQ    → http://localhost:15672  (guest / guest)
```
