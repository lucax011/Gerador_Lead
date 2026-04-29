# Design: Dashboard Completion + AI Quality — Motor de Audiência

**Data:** 2026-04-29  
**Scope:** Fase A (dashboard) + Fase B (IA de compatibilidade)  
**Princípio:** score não é do lead — é da relação lead × oferta.

---

## Contexto

O pipeline event-driven, o modo varredura (sweep), os offer_tags e o dashboard estão funcionais. Dois gaps operacionais bloqueiam o uso em produção:

1. A Nova Pesquisa chama Google Places direto do browser — chave exposta no `localStorage`
2. `sweep_jobs` in-memory perde estado ao reiniciar a API

Fase B melhora a qualidade da análise IA adicionando dados CNPJ e contexto de nicho ao prompt de compatibilidade.

---

## Fase A — Completar o Dashboard

### A1. Backend Search Proxy

**Endpoint:** `POST /api/search`

**Request:**
```json
{
  "terms":        ["nail", "manicure"],
  "city":         "São Paulo",
  "state":        "SP",
  "neighborhood": "Pinheiros",
  "max_results":  20,
  "campanha_id":  "uuid-opcional-ou-null"
}
```

**Response:**
```json
{
  "results": [
    {
      "name":               "Studio Nail SP",
      "address":            "Rua das Flores 42, Pinheiros, São Paulo",
      "phone":              "+55 11 91234-5678",
      "website":            "https://instagram.com/studionailsp",
      "rating":             4.7,
      "reviews":            230,
      "search_tag":         "nail",
      "instagram_username": "studionailsp"
    }
  ],
  "total": 18
}
```

**Funcionamento interno (`api/main.py`):**
- Itera sobre `terms`; para cada um monta `"<term> em <neighborhood>, <city>, <state>"` (ou `"<term> em <city>, <state>"` sem bairro)
- Chama `https://places.googleapis.com/v1/places:searchText` com `settings.google_places_api_key`
- Extrai Instagram de `websiteUri` via regex `instagram\.com/([A-Za-z0-9_.]+)`
- Deduplica por `(name.lower(), phone)` entre termos
- Retorna JSON plano — o frontend renderiza com `renderMapsResults()` sem alteração

**Mudanças no frontend (`index.html`):**
- Remove campo `maps-api-key` e label "API Key do Google Cloud"
- Remove `localStorage.setItem('gplaces_key', apiKey)` e `localStorage.getItem`
- `runMapsSearch()` mantém o loop visual por termo (steps de progresso como hoje), mas cada iteração chama `fetch('/api/search', {method:'POST', body: JSON.stringify({terms:[singleTerm], city, state, neighborhood, max_results})})` em vez do Google direto — preservando o feedback visual por termo
- Se `settings.google_places_api_key` estiver vazio, o endpoint retorna `503` com mensagem clara para configurar `GOOGLE_PLACES_API_KEY` no `.env`

**Config:**
```
GOOGLE_PLACES_API_KEY=<sua-chave-google-places>
```
Já existe em `shared/config.py` como campo `google_places_api_key: str = ""`. Nenhuma mudança de schema de config necessária.

---

### A2. Persistência do sweep_jobs

**Nova tabela:** `sweep_jobs` — migration `0004_sweep_jobs`

```sql
CREATE TABLE sweep_jobs (
    id            UUID         PRIMARY KEY,
    campanha_id   UUID         NOT NULL REFERENCES campanhas(id) ON DELETE CASCADE,
    campanha_name VARCHAR(255),
    status        VARCHAR(20)  NOT NULL DEFAULT 'running',
    total         INTEGER      NOT NULL DEFAULT 0,
    analyzed      INTEGER      NOT NULL DEFAULT 0,
    compatible    INTEGER      NOT NULL DEFAULT 0,
    insufficient  INTEGER      NOT NULL DEFAULT 0,
    feed          JSONB        NOT NULL DEFAULT '[]',
    operator      VARCHAR(3)   NOT NULL DEFAULT 'OR',
    threshold     INTEGER      NOT NULL DEFAULT 70,
    offers_count  INTEGER      NOT NULL DEFAULT 1,
    error         TEXT,
    started_at    TIMESTAMP    NOT NULL,
    completed_at  TIMESTAMP
);

CREATE INDEX idx_sweep_jobs_campanha ON sweep_jobs(campanha_id);
```

**ORM:** `SweepJobORM` adicionado em `shared/database/models.py`

**Estratégia write-through:**

| Momento | Operação |
|---|---|
| Job criado (`POST /api/campanhas/{id}/analisar`) | INSERT |
| Cada lead analisado | UPDATE `analyzed, compatible, insufficient, feed` |
| Status muda (paused / completed / error) | UPDATE `status, completed_at` |
| API inicia (lifespan startup) | UPDATE `status='interrupted'` em todos os jobs `status='running'` |

**Helpers adicionados em `api/main.py`:**
- `async def _db_create_job(session, job_dict) -> None`
- `async def _db_update_job(session, job_id, **fields) -> None`

**`GET /api/campanhas/{id}/progresso`:**
1. Tenta `sweep_jobs` in-memory (processo atual)
2. Se não encontrar, busca no banco pelo `campanha_id` mais recente
3. Retorna o mesmo shape que hoje — frontend não muda

**`sweep_jobs: dict[str, dict]`** mantido como cache de leitura rápida (polling 2s). O dict e o DB ficam sincronizados via write-through.

---

## Fase B — Contexto Rico na IA

### B1. Mover `NICHE_CONTEXTS` para `shared/`

**Novo arquivo:** `shared/niche_contexts.py`
```python
NICHE_CONTEXTS: dict[str, str] = { ... }  # mesmo conteúdo de orchestrator/main.py
```

`orchestrator/main.py` importa de `shared.niche_contexts` — sem mudança de comportamento.  
`api/main.py` também importa para uso no sweep.

### B2. Enriquecer `_build_sweep_lead_profile`

**Assinatura atual:**
```python
def _build_sweep_lead_profile(lead: LeadORM, score_obj: ScoreORM | None) -> str
```

**Nova assinatura:**
```python
def _build_sweep_lead_profile(
    lead: LeadORM,
    score_obj: ScoreORM | None,
    enrichment: EnrichmentORM | None = None,
    niche_context: str | None = None,
) -> str
```

**Bloco CNPJ adicionado ao profile (se `enrichment` presente):**
```
— Empresa (CNPJ.ws) —
Razão social: XYZ Serviços ME
Atividade: Atividades de estética
Porte: MEI
Situação: Ativa
Município: São Paulo SP
Tempo de atividade: 3 anos
```

**Bloco de nicho adicionado (se `niche_context` presente):**
```
— Contexto do nicho —
Beleza/Estética: nail designers, salões, barbearias...
```

**Como o niche_context é resolvido no sweep:**
1. Busca `lead.metadata_["search_tag"]` (ex: `"nail"`)
2. Busca `lead.niche.slug` se `niche_id` preenchido
3. Fallback: `"Nicho não identificado"`
4. Lookup em `NICHE_CONTEXTS` pelo slug/tag

### B3. Novo campo no `SWEEP_PROMPT`

**Adicionado ao JSON de resposta do GPT:**
```json
"score_breakdown": {
  "icp_match":          35,
  "channel_readiness":  28,
  "data_quality":       24
}
```
Soma dos três = `score`. GPT instrui-se a manter consistência (se `score=87`, os três somam 87).

**`offer_tag` salva com novo campo opcional:**
```python
{
  "offer_slug":       "bot-prestador",
  "score":            87,
  "channel":          "whatsapp",
  "tone":             "direto",
  "time":             "19h–21h",
  "reason":           "MEI ativo há 3 anos, Instagram business 2.4k seguidores",
  "score_breakdown":  {"icp_match": 35, "channel_readiness": 28, "data_quality": 24},
  "insufficient_data": false,
  "analyzed_at":      "2026-04-29T..."
}
```
Nenhuma mudança de schema — `score_breakdown` vai dentro do JSONB existente.

### B4. Lead Detail Modal — exibir score_breakdown

Se `offer_tag.score_breakdown` presente, o modal exibe 3 mini-barras:
```
ICP Match        ████████░░  35
Canal pronto     ███████░░░  28
Qualidade dados  ██████░░░░  24
```

**`_run_sweep()` — mudança de carregamento:**
```python
select(LeadORM)
  .options(
      selectinload(LeadORM.scores),
      selectinload(LeadORM.enrichment),   # ← novo
      selectinload(LeadORM.niche),        # ← novo
  )
  .where(LeadORM.id == lead_id)
```

---

## Ordem de implementação

```
Fase A:
  1. migration 0004_sweep_jobs + SweepJobORM
  2. write-through em _run_sweep + helpers _db_create/update_job
  3. GET /api/campanhas/{id}/progresso fallback para DB
  4. POST /api/search + remoção do campo API key no frontend

Fase B:
  5. shared/niche_contexts.py + atualiza imports
  6. _build_sweep_lead_profile com enrichment + niche_context
  7. SWEEP_PROMPT com score_breakdown
  8. Lead detail modal renderiza score_breakdown
```

---

## Arquivos afetados

| Arquivo | Operação |
|---|---|
| `shared/database/models.py` | + `SweepJobORM` |
| `shared/database/migrations/versions/0004_sweep_jobs.py` | novo |
| `shared/niche_contexts.py` | novo |
| `services/api/main.py` | + `POST /api/search`, write-through sweep_jobs, load enrichment/niche no sweep |
| `services/orchestrator/main.py` | import de `shared.niche_contexts` |
| `services/api/static/index.html` | remove campo API key, `runMapsSearch()` → `/api/search`, lead modal score_breakdown |

---

## Invariantes preservadas

- `offer_tags` nunca substitui `score` genérico — layers independentes
- Modo varredura nunca re-analisa lead com offer_tag existente para a mesma campanha
- `LeadStatus` lifecycle não quebrado
- `campanha_id` propagado em todos os eventos
