# Orchestrator Consumer + Worker — Design Spec

**Data:** 2026-05-04  
**Tarefa:** Task 12  
**Branch:** dev

---

## Contexto

Pipeline atual: `Captured → Validated → Deduplicated → Enriched → Scored → [Orchestrated ← novo] → Distributed`

O Scorer calcula qualidade de dados (determinístico, barato). O Orchestrator refina esse score usando GPT-4o-mini com contexto de oferta e decide canal/abordagem de contato. O score final persistido no banco é o do Orchestrator.

**Princípio central:** score é da relação lead × oferta, não do lead sozinho. O Scorer é pré-filtro; o Orchestrator é o árbitro final.

---

## Mudanças de Domínio

### `Score` — suporte a refinamento por IA

Novos campos:
- `AiReason: string?` — justificativa do GPT para o ajuste
- `UpdatedAt: DateTime?` — timestamp da última modificação

Novo método:
```csharp
public void Refine(double adjustment, string reason)
{
    Value = Math.Clamp(Math.Round(Value + adjustment, 2), 0, 100);
    Temperature = Temperature.From(Value); // recalcula HOT/WARM/COLD
    AiReason = reason;
    UpdatedAt = DateTime.UtcNow;
}
```

`ScoreRepository.SaveAsync` passa a fazer upsert real: insert se `Detached`, update (`ExecuteUpdateAsync` ou `Entry.State = Modified`) se já persistido.

### `LeadStatus.Tagged` — revertido

O status `Tagged` adicionado nos uncommitted changes não tem consumidor no pipeline de eventos. Scan mode é assíncrono via API. O status é removido; pipeline: `Scored → Orchestrated → Distributed`.

`AllowedTransitions` volta a ser:
```
Scored → [Orchestrated, Distributed, Rejected]
```

### `Campaign` — integração ao AppDbContext

- `CampaignConfiguration`: tabela `campaigns`, campos `offer_description`, `ideal_customer_profile`, `ticket`, `keywords_alvo` (JSONB)
- `ICampaignRepository`: `FindByIdAsync(Guid, CancellationToken)`
- `CampaignRepository`: implementação EF
- `AppDbContext.Campaigns`: `DbSet<Campaign>`

---

## Abstração da IA

### `IOrchestratorAiClient`

```csharp
public interface IOrchestratorAiClient
{
    Task<OrchestratorOutput> AnalyzeAsync(OrchestratorInput input, CancellationToken ct);
}
```

### `OrchestratorInput`

```csharp
public sealed record OrchestratorInput(
    Guid LeadId,
    string Name,
    string? Phone,
    string? InstagramUsername,
    string? InstagramAccountType,
    int? InstagramFollowers,
    double? InstagramEngagementRate,
    double CurrentScore,
    string Temperature,
    string? CampaignSlug,
    string? OfferDescription,
    string? IdealCustomerProfile,
    string? Ticket
);
```

### `OrchestratorOutput`

```csharp
public sealed record OrchestratorOutput(
    string Approach,        // whatsapp | instagram_dm | nurture | none
    string Tone,
    string BestTime,
    double ScoreAdjustment,
    string OpeningMessage,
    string NeedIdentified,
    string OfferCategory,
    string[] Objections
);
```

### Implementações

**`OpenAiOrchestratorClient`** (prod):
- Chama GPT-4o-mini via HTTP (`IHttpClientFactory`)
- Prompt estruturado com dados do lead + oferta
- Resposta em JSON, parse via `System.Text.Json`
- Registrada quando `OPENAI_API_KEY` presente no ambiente

**`DeterministicOrchestratorClient`** (fallback):
- COLD → `approach = nurture`
- HOT + `InstagramUsername` presente → `approach = instagram_dm`
- HOT + `Phone` presente → `approach = whatsapp`
- Else → `approach = nurture`
- `ScoreAdjustment = 0`, campos de texto com valores padrão
- Registrada quando `OPENAI_API_KEY` ausente

O Worker seleciona a implementação no DI — nenhum `if` no consumer.

---

## `OrchestratorConsumer`

Consome: `LeadScoredMessage`  
Publica: `LeadOrchestratedMessage`

### Fluxo de execução

```
1. FindByIdAsync(msg.LeadId)        → não encontrado: log + return
2. FindByLeadIdAsync(msg.LeadId)    → score do Scorer
3. FindByIdAsync(msg.CampaignId)    → campanha (nullable)
4. Montar OrchestratorInput
5. IOrchestratorAiClient.AnalyzeAsync(input)
6. score.Refine(output.ScoreAdjustment, output.NeedIdentified)
7. ScoreRepository.SaveAsync(score)
8. lead.AdvanceStatus(LeadStatus.Orchestrated)
9. LeadRepository.SaveAsync(lead)
10. Publish LeadOrchestratedMessage
```

### `LeadOrchestratedMessage`

```csharp
public sealed record LeadOrchestratedMessage(
    Guid LeadId,
    Guid? CampaignId,
    string Approach,
    string Tone,
    string BestTime,
    string OpeningMessage,
    double FinalScore,
    string CorrelationId
);
```

### Regras

- **Sem campanha:** campos de oferta `null` → `DeterministicOrchestratorClient` trata normalmente
- **Lead COLD após Refine:** evento publicado normalmente — decisão de não distribuir é do `DistributorConsumer`
- **Sem Score no DB:** log warning + return (estado inconsistente — não deve ocorrer em pipeline normal)

---

## `OrchestratorWorker`

**Projeto:** `api/workers/MotorAudiencia.OrchestratorWorker`

**`Program.cs`:**
- Serilog JSON (padrão dos outros workers)
- MassTransit RabbitMQ, queue `ma-orchestrator`, `PrefetchCount = 5`
- Retry: 5s / 15s / 30s
- DI: `ILeadRepository`, `IScoreRepository`, `ICampaignRepository`
- DI condicional: `OPENAI_API_KEY` presente → `OpenAiOrchestratorClient` + `HttpClient`; ausente → `DeterministicOrchestratorClient`

**`Dockerfile`:** padrão dos outros workers, entry point `MotorAudiencia.OrchestratorWorker`

**`docker-compose.yml`:** serviço `orchestrator` com `env_file: ../.env`

**`.env.example`:** adiciona `OPENAI_API_KEY=`

---

## Migrations

Duas migrations novas (ou combinadas em uma):

**`AddCampaignsTable`:**
- Cria tabela `campaigns` com: `id`, `name`, `slug`, `status`, `offer_description`, `ideal_customer_profile`, `ticket`, `keywords_alvo` (jsonb), `is_active`, `created_at`

**`AddAiReasonToScores`:**
- `scores.ai_reason` (text, nullable)
- `scores.updated_at` (timestamptz, nullable)

---

## Testes

**`OrchestratorConsumerTests`** — MassTransit InMemory, padrão existente.

| # | Cenário | Verifica |
|---|---------|---------|
| 1 | Lead não encontrado | Nenhum evento publicado |
| 2 | Lead COLD, sem campanha, sem API key | `approach = nurture`, `LeadOrchestratedMessage` publicado |
| 3 | Lead HOT com Instagram, sem API key | `approach = instagram_dm` |
| 4 | Lead HOT com telefone e campanha, sem API key | `approach = whatsapp`, score atualizado no DB |
| 5 | `ScoreAdjustment` aplicado corretamente | `FinalScore == Clamp(original + adj, 0, 100)` |

`OpenAiOrchestratorClient` não é testado com chamadas reais — `DeterministicOrchestratorClient` é injetado diretamente nos testes.

---

## Arquivos a criar/modificar

**Criar:**
- `Domain/Events/LeadOrchestratedMessage.cs`
- `Domain/Interfaces/IOrchestratorAiClient.cs`
- `Domain/Interfaces/ICampaignRepository.cs`
- `Infrastructure/AI/OrchestratorInput.cs`
- `Infrastructure/AI/OrchestratorOutput.cs`
- `Infrastructure/AI/OpenAiOrchestratorClient.cs`
- `Infrastructure/AI/DeterministicOrchestratorClient.cs`
- `Infrastructure/Messaging/Consumers/OrchestratorConsumer.cs`
- `Infrastructure/Persistence/Configurations/CampaignConfiguration.cs`
- `Infrastructure/Persistence/Repositories/CampaignRepository.cs`
- `Infrastructure/Persistence/Migrations/YYYYMMDD_AddAiReasonToScores.cs`
- `workers/MotorAudiencia.OrchestratorWorker/Program.cs`
- `workers/MotorAudiencia.OrchestratorWorker/MotorAudiencia.OrchestratorWorker.csproj`
- `workers/MotorAudiencia.OrchestratorWorker/Dockerfile`
- `tests/MotorAudiencia.Tests/Consumers/OrchestratorConsumerTests.cs`

**Modificar:**
- `Domain/Entities/Score.cs` — `Refine()`, `AiReason`, `UpdatedAt`
- `Domain/ValueObjects/LeadStatus.cs` — remover `Tagged`, ajustar `Orchestrated` transitions
- `Domain/Entities/Lead.cs` — manter `TagsJson`/`Tags`/`SetTags` (são tags do scraper Google Places); apenas remover `LeadStatus.Tagged` das transições
- `Infrastructure/Persistence/AppDbContext.cs` — `DbSet<Campaign>`
- `Infrastructure/Persistence/Repositories/ScoreRepository.cs` — upsert real
- `Infrastructure/Persistence/Configurations/LeadConfiguration.cs` — manter `tags`
- `infra/docker-compose.yml` — serviço `orchestrator`
- `.env.example` — `OPENAI_API_KEY=`
