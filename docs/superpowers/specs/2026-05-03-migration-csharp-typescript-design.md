# Spec: Migração para C#/.NET + TypeScript — Motor de Audiência

**Data:** 2026-05-03
**Status:** Aprovado para implementação

---

## 1. Contexto

O Motor de Audiência existe hoje como 12 microserviços Python (FastAPI + workers aio-pika) com frontend em HTML/JS vanilla. O fluxo de ponta a ponta está validado: captação via Google Places → enriquecimento → tagging semântico via IA → sweep de compatibilidade lead × oferta → distribuição.

A migração tem dois objetivos:
1. **Manutenibilidade**: tipagem forte no domínio (.NET), contratos explícitos entre serviços
2. **Clareza arquitetural**: separação real entre domínio (C#), integrações externas (Node.js) e interface (Next.js)

---

## 2. Arquitetura escolhida: Clean Architecture .NET + Node.js sidecar + Next.js

### 2.1 Visão geral

```
Browser
  ↓ HTTPS
Next.js 14 (web/ :3000)
  ↓ route handlers (proxy — browser nunca vê URL do .NET)
.NET 8 API (api/ :5000)  ←→  PostgreSQL 15
  ↓ RabbitMQ (TOPIC exchange "leads")
.NET Workers — Validator, Deduplicator, Scorer, Enricher
  ↓ RabbitMQ
Node.js Services — Tagger, Orchestrator, Scraper, Outreach, Notification
  ↓ HMAC → .NET API (persistência de resultados)
```

### 2.2 Monorepo

```
gerador-lead/
├── api/                    ← .NET 8 Clean Architecture
├── services/               ← Node.js/TypeScript (integrações externas)
│   ├── tagger/
│   ├── orchestrator/
│   ├── scraper/
│   ├── outreach/
│   └── notification/
├── web/                    ← Next.js 14 App Router + TypeScript
├── shared/
│   └── contracts/          ← JSON Schema / OpenAPI gerados do .NET
└── infra/
    ├── docker-compose.yml
    ├── docker-compose.prod.yml
    └── postgres/
```

### 2.3 Divisão de responsabilidades

| Camada | Tecnologia | Responsabilidade |
|---|---|---|
| `api/` | C# .NET 8 | Domínio, pipeline (Validator→Scorer), REST API, JWT, SignalR |
| `services/` | Node.js + TypeScript | Integrações externas: OpenAI, Google Places, WhatsApp, Telegram |
| `web/` | Next.js 14 + TypeScript | Dashboard, Nova Pesquisa, leads, campanhas |
| `shared/contracts/` | OpenAPI / JSON Schema | Gerado automaticamente via `dotnet-openapi` do .NET — fonte única de verdade dos tipos |
| `infra/` | YAML / SQL | Docker Compose dev + prod, migrations |

### 2.4 Pipeline mapeado

```
Scraper (Node.js) → lead.captured
  ↓
Validator (.NET Worker) → lead.validated
  ↓
Deduplicator (.NET Worker) → lead.deduplicated
  ↓
Enricher (.NET Worker, CNPJ.ws via HttpClient) → lead.enriched
  ↓
Scorer (.NET Worker, lógica de domínio pura) → lead.scored
  ↓
Tagger (Node.js, OpenAI GPT-4o-mini) → lead.tagged
  ↓
Orchestrator (Node.js, OpenAI GPT-4o-mini) → lead.orchestrated
  ↓
Notification (Node.js, Telegram) → lead.distributed
  ↓
Outreach (Node.js, Evolution API WhatsApp) → lead.contacted
```

Sweep (varredura por campanha): `POST /api/campanhas/{id}/analisar` (.NET) → publica evento `sweep.job.created` no RabbitMQ → Orchestrator (Node.js) consome, analisa lead × oferta, chama .NET via HMAC para persistir `offer_tags` → progresso transmitido via SignalR `SweepProgressHub` para o frontend em tempo real.

---

## 3. .NET Clean Architecture

### 3.1 Estrutura de camadas

```
api/
├── Domain/
│   ├── Entities/        Lead, Campaign, Source, Niche, SweepJob
│   ├── ValueObjects/    LeadStatus, Score, Temperature, OfferTag
│   ├── Events/          LeadCaptured, LeadScored, LeadTagged, ...
│   └── Interfaces/      ILeadRepository, IBroker, IScoringEngine
│
├── Application/
│   ├── UseCases/        ValidateLead, DeduplicateLead, ScoreLead, RunSweep
│   ├── DTOs/            LeadDto, CampaignDto, SweepProgressDto
│   ├── Validators/      FluentValidation por DTO de entrada
│   └── Interfaces/      ILeadService, IScoringEngine, ITokenService
│
├── Infrastructure/
│   ├── Persistence/     EF Core, repositórios, migrations
│   ├── Messaging/       MassTransit (RabbitMQ) — publisher + consumers
│   ├── Workers/         ValidatorWorker, DeduplicatorWorker, ScorerWorker, EnricherWorker
│   ├── Http/            CnpjWsClient (HttpClientFactory, retry Polly, timeout)
│   └── Security/        ArgonPasswordHasher, JwtService, HmacValidator
│
└── Presentation/
    ├── Controllers/     AuthController, LeadsController, CampaignsController
    ├── Hubs/            SweepProgressHub (SignalR)
    └── Middleware/      ErrorHandling, RateLimiting, SecurityHeaders, RequestLogging
```

### 3.2 Mensageria

MassTransit sobre RabbitMQ. Cada worker é um `IConsumer<TMessage>` registrado via `AddMassTransit`. Dead-letter configurado por fila. Correlation ID propagado em todas as mensagens.

---

## 4. Serviços Node.js/TypeScript

### 4.1 Estrutura padrão de cada serviço

```
services/<nome>/
├── src/
│   ├── config.ts        ← Zod: valida env vars no startup
│   ├── consumer.ts      ← RabbitMQ consumer tipado (amqplib)
│   ├── publisher.ts     ← RabbitMQ publisher tipado
│   ├── ai/              ← (tagger, orchestrator apenas)
│   │   ├── prompt.ts    ← Template tipado
│   │   ├── sanitizer.ts ← Sanitiza input + mascara PII
│   │   └── validator.ts ← Valida output com Zod
│   └── index.ts         ← Entry point
├── Dockerfile
└── package.json
```

### 4.2 Config com Zod

Toda variável de ambiente declarada em `config.ts` com Zod. Serviço falha imediatamente na inicialização se qualquer variável obrigatória estiver ausente. Nunca sobe com configuração silenciosamente inválida.

```typescript
const EnvSchema = z.object({
  RABBITMQ_URL:    z.string().url(),
  OPENAI_API_KEY:  z.string().min(20),
  SERVICE_SECRET:  z.string().min(32),
  API_BASE_URL:    z.string().url(),
});
export const config = EnvSchema.parse(process.env);
```

### 4.3 Pipeline de segurança nos prompts de IA

Aplicado obrigatoriamente antes de qualquer chamada OpenAI:

```
Input bruto (dados do lead)
  → sanitize()      remove < > " ' ; \n \r
  → maskPii()       email→[EMAIL], phone→[PHONE], CNPJ→[CNPJ]
  → truncate()      bio≤200, nome≤60, atividade≤100
  → buildPrompt()   template tipado, sem concatenação livre
  → openai.chat()   max_tokens fixo (tagger=300, orchestrator=500, sweep=400)
  → validateOutput() Zod schema — rejeita se fora do contrato
  → auditLog()      loga com PII mascarado + correlation ID
```

Output inválido da IA vai para dead-letter — nunca propaga dado não validado.

---

## 5. Frontend Next.js 14

### 5.1 Estrutura

```
web/
├── app/
│   ├── (auth)/login/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx            ← layout protegido
│   │   ├── page.tsx              ← visão geral / métricas
│   │   ├── leads/[id]/page.tsx   ← perfil + offer_tags
│   │   ├── campanhas/[id]/page.tsx ← sweep + progresso
│   │   └── pesquisa/page.tsx     ← Nova Pesquisa
│   └── api/auth/                 ← route handlers: login, refresh, logout
├── components/
│   ├── ui/                       ← shadcn/ui (Radix + Tailwind)
│   ├── leads/
│   ├── campaigns/
│   └── layout/
├── lib/
│   ├── api-client.ts             ← cliente tipado gerado do OpenAPI .NET
│   ├── auth.ts                   ← leitura cookie JWT
│   └── validations.ts            ← Zod schemas espelhando contracts/
└── middleware.ts                 ← redireciona /login se sem token
```

### 5.2 Decisões técnicas

| Aspecto | Escolha |
|---|---|
| UI | shadcn/ui + Tailwind CSS |
| Forms | React Hook Form + Zod |
| Server state | TanStack Query |
| Real-time (sweep) | Server-Sent Events |
| Auth storage | Cookie httpOnly exclusivamente |

### 5.3 Proxy pattern

Todas as chamadas à API .NET passam por route handlers do Next.js. O browser nunca vê a URL do .NET nem o `SERVICE_SECRET`. Token JWT lido apenas server-side.

---

## 6. Segurança

### 6.1 Autenticação e senhas

- **Argon2id** com `memory=65536`, `iterations=3`, `parallelism=1`
- **Pepper** por ambiente (`AUTH_PEPPER`, mínimo 32 chars) concatenado antes do hash — banco vazado sem pepper é inútil
- **JWT** access token 15min + refresh token 7 dias (cookie `httpOnly; Secure; SameSite=Strict`)
- Refresh token com **rotation family** — reuso de token roubado invalida toda a família
- Um único usuário admin no sistema

### 6.2 Comunicação entre serviços

HMAC-SHA256 por requisição em cada chamada Node.js → .NET:

```typescript
header "X-Service-Signature": HMAC(timestamp + body, SERVICE_SECRET)
header "X-Service-Timestamp": epoch ms
```

Janela de validade: 30 segundos. Replay attack inviável.

### 6.3 Rate limiting

- 100 req/min por IP (global)
- 10 req/min no endpoint de login (proteção brute force)
- Sliding window via ASP.NET Core RateLimiter middleware

### 6.4 Headers HTTP

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), camera=()
```

### 6.5 Validação de inputs

- FluentValidation em todos os DTOs .NET antes de qualquer use case
- EF Core com queries parametrizadas exclusivamente — zero SQL interpolado
- Zod em todos os inputs dos serviços Node.js

### 6.6 Secrets

Todas as variáveis obrigatórias validadas no startup (.NET: `IOptions<T>` com DataAnnotations, Node.js: Zod). `.env` nunca commitado. `.env.example` com chaves sem valores commitado como contrato.

### 6.7 Logging

Serilog (.NET) e Pino (Node.js), ambos com output JSON estruturado. PII mascarado na camada de infraestrutura antes de logar. Correlation ID propagado em todas as mensagens e requisições.

---

## 7. Infraestrutura Docker

### 7.1 docker-compose.yml (dev)

```yaml
services:
  postgres:      postgres:15-alpine
  rabbitmq:      rabbitmq:3.12-management-alpine
  pgadmin:       dpage/pgadmin4          # dev apenas
  api:           api/Dockerfile          # :5000
  web:           web/Dockerfile          # :3000
  tagger:        services/tagger/
  orchestrator:  services/orchestrator/
  scraper:       services/scraper/
  outreach:      services/outreach/
  notification:  services/notification/
```

### 7.2 Produção

`docker-compose.prod.yml` como override:
- Remove pgadmin
- Adiciona Traefik como reverse proxy com TLS automático (Let's Encrypt)
- Secrets via variáveis de ambiente do host ou Docker Secrets
- Health checks em todos os serviços

### 7.3 Variáveis de ambiente obrigatórias

```bash
# .env.example
DATABASE_URL=
RABBITMQ_URL=
JWT_SECRET=               # mínimo 64 chars
AUTH_PEPPER=              # mínimo 32 chars
SERVICE_SECRET=           # mínimo 32 chars — HMAC entre .NET e Node.js
OPENAI_API_KEY=
GOOGLE_PLACES_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=
```

---

## 8. Roadmap de implementação (ordem sugerida)

1. **Infra base** — monorepo, Docker Compose, PostgreSQL, RabbitMQ
2. **API .NET** — estrutura Clean Architecture, auth JWT/Argon2id, endpoint de health
3. **Workers .NET** — Validator, Deduplicator, Scorer, Enricher
4. **Services Node.js** — Tagger e Orchestrator (IA) primeiro, depois Scraper, Notification, Outreach
5. **Frontend Next.js** — auth flow → dashboard → leads → campanhas → pesquisa
6. **Sweep** — endpoint .NET + SignalR + progresso em tempo real no frontend
7. **Produção** — docker-compose.prod.yml + Traefik + secrets

---

## 9. Débitos conhecidos / decisões futuras

| Item | Decisão atual | Futuro |
|---|---|---|
| Message broker | RabbitMQ | Avaliar Redis Streams após estabilização |
| Enriquecimento pago | BigDataCorp / Serasa: stubs | Implementar quando houver contrato |
| Instagram DM | Stub em outreach | Avaliar Facebook Graph API |
| Multi-tenant | Usuário único admin | Avaliar após MVP |
| CI/CD | Docker Compose manual | GitHub Actions para build + push |
