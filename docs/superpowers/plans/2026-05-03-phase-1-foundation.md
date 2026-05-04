# Motor de Audiência — Fase 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o monorepo, infraestrutura Docker, estrutura Clean Architecture .NET 8, autenticação JWT + Argon2id com usuário admin único seedado e todos os middlewares de segurança ativos.

**Architecture:** .NET 8 Web API com camadas Domain / Application / Infrastructure / Presentation. Auth via JWT (15min) + refresh token com rotation family (7 dias, cookie httpOnly). Senhas com Argon2id + pepper. Comunicação serviço-a-serviço via HMAC-SHA256.

**Tech Stack:** .NET 8, EF Core 8, Npgsql, Argon2id (Konscious), FluentValidation, Serilog, xUnit, FluentAssertions, Moq, Docker Compose, PostgreSQL 15, RabbitMQ 3.12

---

## AS-IS → TO-BE

**AS-IS:** Projeto Python existente em `lead-generator/`. Sem estrutura C#/TypeScript. Sem autenticação. Docker Compose com workers Python.

**TO-BE:** Monorepo com pastas `api/`, `services/`, `web/`, `infra/`. API .NET 8 rodando em `:5000` com login funcional, token refresh, headers de segurança, rate limiting e usuário admin seedado via variável de ambiente.

---

## Mapa de arquivos

```
gerador-lead/
├── api/
│   ├── MotorAudiencia.sln
│   ├── src/
│   │   ├── MotorAudiencia.Domain/
│   │   │   ├── Entities/
│   │   │   │   ├── Lead.cs
│   │   │   │   ├── Campaign.cs
│   │   │   │   ├── Source.cs
│   │   │   │   └── User.cs
│   │   │   ├── ValueObjects/
│   │   │   │   ├── LeadStatus.cs
│   │   │   │   └── RefreshToken.cs
│   │   │   └── Interfaces/
│   │   │       ├── IPasswordHasher.cs
│   │   │       ├── IJwtService.cs
│   │   │       └── IUserRepository.cs
│   │   ├── MotorAudiencia.Application/
│   │   │   ├── UseCases/Auth/
│   │   │   │   ├── LoginUseCase.cs
│   │   │   │   └── RefreshTokenUseCase.cs
│   │   │   ├── DTOs/
│   │   │   │   ├── LoginRequest.cs
│   │   │   │   └── LoginResponse.cs
│   │   │   └── Validators/
│   │   │       └── LoginRequestValidator.cs
│   │   ├── MotorAudiencia.Infrastructure/
│   │   │   ├── Persistence/
│   │   │   │   ├── AppDbContext.cs
│   │   │   │   ├── Configurations/UserConfiguration.cs
│   │   │   │   ├── Repositories/UserRepository.cs
│   │   │   │   └── Migrations/
│   │   │   └── Security/
│   │   │       ├── Argon2idPasswordHasher.cs
│   │   │       ├── JwtService.cs
│   │   │       └── HmacValidator.cs
│   │   └── MotorAudiencia.API/
│   │       ├── Controllers/AuthController.cs
│   │       ├── Middleware/
│   │       │   ├── SecurityHeadersMiddleware.cs
│   │       │   └── HmacAuthMiddleware.cs
│   │       ├── Options/
│   │       │   ├── JwtOptions.cs
│   │       │   └── SecurityOptions.cs
│   │       ├── Startup/
│   │       │   └── DatabaseSeeder.cs
│   │       └── Program.cs
│   └── tests/
│       └── MotorAudiencia.Tests/
│           ├── Security/
│           │   ├── Argon2idPasswordHasherTests.cs
│           │   └── JwtServiceTests.cs
│           └── UseCases/
│               └── LoginUseCaseTests.cs
├── infra/
│   ├── docker-compose.yml
│   └── postgres/init.sql
└── .env.example
```

---

## Task 1: Estrutura do monorepo

**Files:**
- Create: `api/` (diretório)
- Create: `services/` (diretório)
- Create: `web/` (diretório)
- Create: `infra/docker-compose.yml`
- Create: `infra/postgres/init.sql`
- Create: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Criar estrutura de pastas**

```bash
mkdir -p api services web infra/postgres
```

- [ ] **Step 2: Criar .env.example**

```bash
# .env.example — commitar sem valores reais
cat > .env.example << 'EOF'
# Database
POSTGRES_DB=motor_audiencia
POSTGRES_USER=ma_user
POSTGRES_PASSWORD=
DATABASE_URL=Host=postgres;Database=motor_audiencia;Username=ma_user;Password=

# RabbitMQ
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=
RABBITMQ_URL=amqp://guest:@rabbitmq:5672/

# Auth
JWT_SECRET=
JWT_ISSUER=motor-audiencia
JWT_AUDIENCE=motor-audiencia-client
AUTH_PEPPER=
ADMIN_USERNAME=admin
ADMIN_PASSWORD=

# Service-to-service HMAC
SERVICE_SECRET=

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Google Places
GOOGLE_PLACES_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# WhatsApp (Evolution API)
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=
EOF
```

- [ ] **Step 3: Criar docker-compose.yml**

```yaml
# infra/docker-compose.yml
x-worker-base: &worker-base
  restart: unless-stopped
  env_file: ../.env
  networks:
    - ma-net
  depends_on:
    postgres:
      condition: service_healthy
    rabbitmq:
      condition: service_healthy

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-motor_audiencia}
      POSTGRES_USER: ${POSTGRES_USER:-ma_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432:5432"
    networks:
      - ma-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-ma_user} -d ${POSTGRES_DB:-motor_audiencia}"]
      interval: 10s
      timeout: 5s
      retries: 5

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-guest}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    networks:
      - ma-net
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@admin.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    networks:
      - ma-net
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  api:
    <<: *worker-base
    build:
      context: ../api
      dockerfile: Dockerfile
    container_name: ma-api
    ports:
      - "5000:5000"

networks:
  ma-net:
    driver: bridge

volumes:
  postgres-data:
  rabbitmq-data:
```

- [ ] **Step 4: Criar infra/postgres/init.sql**

```sql
-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
```

- [ ] **Step 5: Atualizar .gitignore**

Adicionar ao `.gitignore` existente:

```
# .NET
api/bin/
api/obj/
api/**/.vs/
*.user
*.suo

# Node
services/*/node_modules/
web/node_modules/
web/.next/

# Env
.env
!.env.example

# Superpowers
.superpowers/
```

- [ ] **Step 6: Verificar estrutura**

```bash
ls -la
# Esperado: api/ infra/ services/ web/ .env.example
ls infra/
# Esperado: docker-compose.yml postgres/
```

- [ ] **Step 7: Commit**

```bash
git add infra/ .env.example .gitignore
git commit -m "chore: monorepo structure + docker compose"
```

---

## Task 2: .NET solution skeleton

**Files:**
- Create: `api/MotorAudiencia.sln`
- Create: `api/src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj`
- Create: `api/src/MotorAudiencia.Application/MotorAudiencia.Application.csproj`
- Create: `api/src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj`
- Create: `api/src/MotorAudiencia.API/MotorAudiencia.API.csproj`
- Create: `api/tests/MotorAudiencia.Tests/MotorAudiencia.Tests.csproj`

- [ ] **Step 1: Criar solution e projetos**

```bash
cd api

dotnet new sln -n MotorAudiencia

dotnet new classlib -n MotorAudiencia.Domain     -o src/MotorAudiencia.Domain     -f net8.0
dotnet new classlib -n MotorAudiencia.Application -o src/MotorAudiencia.Application -f net8.0
dotnet new classlib -n MotorAudiencia.Infrastructure -o src/MotorAudiencia.Infrastructure -f net8.0
dotnet new webapi   -n MotorAudiencia.API        -o src/MotorAudiencia.API        -f net8.0 --no-openapi
dotnet new xunit    -n MotorAudiencia.Tests      -o tests/MotorAudiencia.Tests    -f net8.0

dotnet sln add src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj
dotnet sln add src/MotorAudiencia.Application/MotorAudiencia.Application.csproj
dotnet sln add src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj
dotnet sln add src/MotorAudiencia.API/MotorAudiencia.API.csproj
dotnet sln add tests/MotorAudiencia.Tests/MotorAudiencia.Tests.csproj
```

- [ ] **Step 2: Adicionar referências entre projetos**

```bash
dotnet add src/MotorAudiencia.Application/MotorAudiencia.Application.csproj reference \
  src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj

dotnet add src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj reference \
  src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj \
  src/MotorAudiencia.Application/MotorAudiencia.Application.csproj

dotnet add src/MotorAudiencia.API/MotorAudiencia.API.csproj reference \
  src/MotorAudiencia.Application/MotorAudiencia.Application.csproj \
  src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj

dotnet add tests/MotorAudiencia.Tests/MotorAudiencia.Tests.csproj reference \
  src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj \
  src/MotorAudiencia.Application/MotorAudiencia.Application.csproj \
  src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj
```

- [ ] **Step 3: Adicionar pacotes NuGet**

```bash
# Domain — sem dependências externas (propositalmente)

# Application
dotnet add src/MotorAudiencia.Application package FluentValidation --version 11.*
dotnet add src/MotorAudiencia.Application package Microsoft.Extensions.Options --version 8.*

# Infrastructure
dotnet add src/MotorAudiencia.Infrastructure package Microsoft.EntityFrameworkCore --version 8.*
dotnet add src/MotorAudiencia.Infrastructure package Npgsql.EntityFrameworkCore.PostgreSQL --version 8.*
dotnet add src/MotorAudiencia.Infrastructure package Microsoft.EntityFrameworkCore.Design --version 8.*
dotnet add src/MotorAudiencia.Infrastructure package Konscious.Security.Cryptography.Argon2 --version 1.3.*
dotnet add src/MotorAudiencia.Infrastructure package Microsoft.AspNetCore.Authentication.JwtBearer --version 8.*

# API
dotnet add src/MotorAudiencia.API package Serilog.AspNetCore --version 8.*
dotnet add src/MotorAudiencia.API package Serilog.Sinks.Console --version 5.*
dotnet add src/MotorAudiencia.API package FluentValidation.AspNetCore --version 11.*
dotnet add src/MotorAudiencia.API package Swashbuckle.AspNetCore --version 6.*

# Tests
dotnet add tests/MotorAudiencia.Tests package FluentAssertions --version 6.*
dotnet add tests/MotorAudiencia.Tests package Moq --version 4.*
dotnet add tests/MotorAudiencia.Tests package Microsoft.AspNetCore.Mvc.Testing --version 8.*
```

- [ ] **Step 4: Verificar build**

```bash
dotnet build
# Esperado: Build succeeded. 0 Error(s). 0 Warning(s).
```

- [ ] **Step 5: Commit**

```bash
git add api/
git commit -m "chore: dotnet solution skeleton com Clean Architecture"
```

---

## Task 3: Domain entities

**Files:**
- Create: `api/src/MotorAudiencia.Domain/Entities/User.cs`
- Create: `api/src/MotorAudiencia.Domain/Entities/Lead.cs`
- Create: `api/src/MotorAudiencia.Domain/Entities/Campaign.cs`
- Create: `api/src/MotorAudiencia.Domain/ValueObjects/LeadStatus.cs`
- Create: `api/src/MotorAudiencia.Domain/ValueObjects/RefreshToken.cs`
- Create: `api/src/MotorAudiencia.Domain/Interfaces/IPasswordHasher.cs`
- Create: `api/src/MotorAudiencia.Domain/Interfaces/IJwtService.cs`
- Create: `api/src/MotorAudiencia.Domain/Interfaces/IUserRepository.cs`

- [ ] **Step 1: Criar LeadStatus**

```csharp
// Domain/ValueObjects/LeadStatus.cs
namespace MotorAudiencia.Domain.ValueObjects;

public enum LeadStatus
{
    Captured,
    Validated,
    Deduplicated,
    Enriched,
    Scored,
    Tagged,
    Orchestrated,
    Distributed,
    Contacted,
    Replied,
    Converted,
    Churned,
    Rejected,
}
```

- [ ] **Step 2: Criar RefreshToken value object**

```csharp
// Domain/ValueObjects/RefreshToken.cs
namespace MotorAudiencia.Domain.ValueObjects;

public sealed class RefreshToken
{
    public string Token { get; init; } = string.Empty;
    public Guid FamilyId { get; init; }
    public DateTime ExpiresAt { get; init; }
    public DateTime CreatedAt { get; init; } = DateTime.UtcNow;
    public bool IsRevoked { get; private set; }

    public bool IsExpired => DateTime.UtcNow > ExpiresAt;
    public bool IsActive => !IsRevoked && !IsExpired;

    public void Revoke() => IsRevoked = true;
}
```

- [ ] **Step 3: Criar User entity**

```csharp
// Domain/Entities/User.cs
namespace MotorAudiencia.Domain.Entities;

public sealed class User
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    public string Username { get; private set; } = string.Empty;
    public string PasswordHash { get; private set; } = string.Empty;
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;
    public List<RefreshTokenEntity> RefreshTokens { get; private set; } = [];

    private User() { }

    public static User Create(string username, string passwordHash)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(username);
        ArgumentException.ThrowIfNullOrWhiteSpace(passwordHash);
        return new User { Username = username.ToLowerInvariant(), PasswordHash = passwordHash };
    }
}
```

- [ ] **Step 4: Criar Lead entity (esqueleto — campos completos na Fase 2)**

```csharp
// Domain/Entities/Lead.cs
namespace MotorAudiencia.Domain.Entities;

public sealed class Lead
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    public string Name { get; private set; } = string.Empty;
    public string Email { get; private set; } = string.Empty;
    public string? Phone { get; private set; }
    public string? Company { get; private set; }
    public LeadStatus Status { get; private set; } = LeadStatus.Captured;
    public Guid? CampaignId { get; private set; }
    public Dictionary<string, object> Metadata { get; private set; } = [];
    public List<string> Tags { get; private set; } = [];
    public string? PerfilResumido { get; private set; }
    public List<Dictionary<string, object>> OfferTags { get; private set; } = [];
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; private set; } = DateTime.UtcNow;

    private Lead() { }

    public static Lead Create(string name, string email, string? phone = null, string? company = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        ArgumentException.ThrowIfNullOrWhiteSpace(email);
        return new Lead { Name = name, Email = email.ToLowerInvariant(), Phone = phone, Company = company };
    }

    public void AdvanceStatus(LeadStatus next) => Status = next;
}
```

- [ ] **Step 5: Criar interfaces do domínio**

```csharp
// Domain/Interfaces/IPasswordHasher.cs
namespace MotorAudiencia.Domain.Interfaces;

public interface IPasswordHasher
{
    string Hash(string password);
    bool Verify(string password, string storedHash);
}
```

```csharp
// Domain/Interfaces/IJwtService.cs
namespace MotorAudiencia.Domain.Interfaces;

public interface IJwtService
{
    string GenerateAccessToken(User user);
    RefreshTokenEntity GenerateRefreshToken(Guid familyId);
    Guid? ValidateAccessToken(string token);
}
```

```csharp
// Domain/Interfaces/IUserRepository.cs
namespace MotorAudiencia.Domain.Interfaces;

public interface IUserRepository
{
    Task<User?> FindByUsernameAsync(string username, CancellationToken ct = default);
    Task<User?> FindByRefreshTokenAsync(string token, CancellationToken ct = default);
    Task SaveAsync(User user, CancellationToken ct = default);
}
```

- [ ] **Step 6: Build para verificar**

```bash
cd api && dotnet build src/MotorAudiencia.Domain
# Esperado: Build succeeded.
```

- [ ] **Step 7: Commit**

```bash
git add api/src/MotorAudiencia.Domain/
git commit -m "feat(domain): entities User e Lead + interfaces de auth"
```

---

## Task 4: Implementação de segurança — Argon2id + JWT

**Files:**
- Create: `api/src/MotorAudiencia.Infrastructure/Security/Argon2idPasswordHasher.cs`
- Create: `api/src/MotorAudiencia.Infrastructure/Security/JwtService.cs`
- Create: `api/src/MotorAudiencia.Infrastructure/Security/HmacValidator.cs`
- Create: `api/src/MotorAudiencia.API/Options/SecurityOptions.cs`
- Create: `api/src/MotorAudiencia.API/Options/JwtOptions.cs`
- Create: `api/tests/MotorAudiencia.Tests/Security/Argon2idPasswordHasherTests.cs`
- Create: `api/tests/MotorAudiencia.Tests/Security/JwtServiceTests.cs`

- [ ] **Step 1: Escrever testes do PasswordHasher (TDD — falham primeiro)**

```csharp
// tests/MotorAudiencia.Tests/Security/Argon2idPasswordHasherTests.cs
namespace MotorAudiencia.Tests.Security;

public class Argon2idPasswordHasherTests
{
    private readonly Argon2idPasswordHasher _sut;

    public Argon2idPasswordHasherTests()
    {
        var options = Options.Create(new SecurityOptions { AuthPepper = "test-pepper-32-chars-minimum-ok!" });
        _sut = new Argon2idPasswordHasher(options);
    }

    [Fact]
    public void Hash_SamePassword_ProducesDifferentHashes()
    {
        var hash1 = _sut.Hash("senha123");
        var hash2 = _sut.Hash("senha123");
        hash1.Should().NotBe(hash2); // salt aleatório
    }

    [Fact]
    public void Verify_CorrectPassword_ReturnsTrue()
    {
        var hash = _sut.Hash("minha-senha");
        _sut.Verify("minha-senha", hash).Should().BeTrue();
    }

    [Fact]
    public void Verify_WrongPassword_ReturnsFalse()
    {
        var hash = _sut.Hash("minha-senha");
        _sut.Verify("senha-errada", hash).Should().BeFalse();
    }

    [Fact]
    public void Verify_TamperedHash_ReturnsFalse()
    {
        var hash = _sut.Hash("senha");
        var tampered = hash[..^4] + "XXXX";
        _sut.Verify("senha", tampered).Should().BeFalse();
    }
}
```

- [ ] **Step 2: Rodar testes — verificar que falham**

```bash
cd api && dotnet test tests/MotorAudiencia.Tests --filter "FullyQualifiedName~PasswordHasher"
# Esperado: FAIL — Argon2idPasswordHasher não existe ainda
```

- [ ] **Step 3: Criar SecurityOptions e JwtOptions**

```csharp
// API/Options/SecurityOptions.cs
namespace MotorAudiencia.API.Options;

public sealed class SecurityOptions
{
    public const string Section = "Security";
    [Required, MinLength(32)] public string AuthPepper { get; set; } = string.Empty;
    [Required, MinLength(32)] public string ServiceSecret { get; set; } = string.Empty;
}
```

```csharp
// API/Options/JwtOptions.cs
namespace MotorAudiencia.API.Options;

public sealed class JwtOptions
{
    public const string Section = "Jwt";
    [Required, MinLength(64)] public string Secret { get; set; } = string.Empty;
    [Required] public string Issuer { get; set; } = string.Empty;
    [Required] public string Audience { get; set; } = string.Empty;
    public int AccessTokenMinutes { get; set; } = 15;
    public int RefreshTokenDays { get; set; } = 7;
}
```

- [ ] **Step 4: Implementar Argon2idPasswordHasher**

```csharp
// Infrastructure/Security/Argon2idPasswordHasher.cs
namespace MotorAudiencia.Infrastructure.Security;

public sealed class Argon2idPasswordHasher : IPasswordHasher
{
    private const int MemorySize = 65536;
    private const int Iterations = 3;
    private const int DegreeOfParallelism = 1;
    private const int HashLength = 32;
    private const int SaltLength = 16;

    private readonly string _pepper;

    public Argon2idPasswordHasher(IOptions<SecurityOptions> options)
        => _pepper = options.Value.AuthPepper;

    public string Hash(string password)
    {
        var salt = RandomNumberGenerator.GetBytes(SaltLength);
        var hash = ComputeHash(password, salt);
        return $"{Convert.ToBase64String(salt)}:{Convert.ToBase64String(hash)}";
    }

    public bool Verify(string password, string storedHash)
    {
        var parts = storedHash.Split(':');
        if (parts.Length != 2) return false;
        try
        {
            var salt = Convert.FromBase64String(parts[0]);
            var expected = Convert.FromBase64String(parts[1]);
            var actual = ComputeHash(password, salt);
            return CryptographicOperations.FixedTimeEquals(actual, expected);
        }
        catch
        {
            return false;
        }
    }

    private byte[] ComputeHash(string password, byte[] salt)
    {
        var pepperedBytes = Encoding.UTF8.GetBytes(password + _pepper);
        using var argon2 = new Argon2id(pepperedBytes)
        {
            Salt = salt,
            MemorySize = MemorySize,
            Iterations = Iterations,
            DegreeOfParallelism = DegreeOfParallelism,
        };
        return argon2.GetBytes(HashLength);
    }
}
```

- [ ] **Step 5: Rodar testes — verificar que passam**

```bash
cd api && dotnet test tests/MotorAudiencia.Tests --filter "FullyQualifiedName~PasswordHasher"
# Esperado: 4 passed
```

- [ ] **Step 6: Implementar JwtService**

```csharp
// Infrastructure/Security/JwtService.cs
namespace MotorAudiencia.Infrastructure.Security;

public sealed class JwtService : IJwtService
{
    private readonly JwtOptions _options;

    public JwtService(IOptions<JwtOptions> options) => _options = options.Value;

    public string GenerateAccessToken(User user)
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_options.Secret));
        var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
        var claims = new[]
        {
            new Claim(JwtRegisteredClaimNames.Sub, user.Id.ToString()),
            new Claim(JwtRegisteredClaimNames.UniqueName, user.Username),
            new Claim(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
        };
        var token = new JwtSecurityToken(
            issuer: _options.Issuer,
            audience: _options.Audience,
            claims: claims,
            expires: DateTime.UtcNow.AddMinutes(_options.AccessTokenMinutes),
            signingCredentials: creds);
        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    public RefreshTokenEntity GenerateRefreshToken(Guid familyId) => new()
    {
        Token = Convert.ToBase64String(RandomNumberGenerator.GetBytes(64)),
        FamilyId = familyId,
        ExpiresAt = DateTime.UtcNow.AddDays(_options.RefreshTokenDays),
    };

    public Guid? ValidateAccessToken(string token)
    {
        try
        {
            var handler = new JwtSecurityTokenHandler();
            var key = Encoding.UTF8.GetBytes(_options.Secret);
            handler.ValidateToken(token, new TokenValidationParameters
            {
                ValidateIssuerSigningKey = true,
                IssuerSigningKey = new SymmetricSecurityKey(key),
                ValidateIssuer = true,
                ValidIssuer = _options.Issuer,
                ValidateAudience = true,
                ValidAudience = _options.Audience,
                ClockSkew = TimeSpan.Zero,
            }, out var validated);
            var jwt = (JwtSecurityToken)validated;
            return Guid.Parse(jwt.Subject);
        }
        catch { return null; }
    }
}
```

- [ ] **Step 7: Implementar HmacValidator (serviço-a-serviço)**

```csharp
// Infrastructure/Security/HmacValidator.cs
namespace MotorAudiencia.Infrastructure.Security;

public sealed class HmacValidator
{
    private const int MaxAgeSeconds = 30;
    private readonly string _secret;

    public HmacValidator(IOptions<SecurityOptions> options)
        => _secret = options.Value.ServiceSecret;

    public bool IsValid(string timestamp, string body, string signature)
    {
        if (!long.TryParse(timestamp, out var ts)) return false;
        var age = Math.Abs(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - ts);
        if (age > MaxAgeSeconds * 1000) return false;

        var expected = ComputeHmac(timestamp + body);
        return CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(expected),
            Encoding.UTF8.GetBytes(signature));
    }

    private string ComputeHmac(string data)
    {
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(_secret));
        return Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(data))).ToLower();
    }
}
```

- [ ] **Step 8: Commit**

```bash
git add api/src/MotorAudiencia.Infrastructure/Security/ \
        api/src/MotorAudiencia.API/Options/ \
        api/tests/MotorAudiencia.Tests/Security/
git commit -m "feat(security): Argon2id + JWT com rotation + HMAC validator"
```

---

## Task 5: EF Core + migration inicial

**Files:**
- Create: `api/src/MotorAudiencia.Infrastructure/Persistence/AppDbContext.cs`
- Create: `api/src/MotorAudiencia.Infrastructure/Persistence/Configurations/UserConfiguration.cs`
- Create: `api/src/MotorAudiencia.Infrastructure/Persistence/Entities/RefreshTokenEntity.cs`
- Create: `api/src/MotorAudiencia.Infrastructure/Persistence/Repositories/UserRepository.cs`

- [ ] **Step 1: Criar RefreshTokenEntity (tabela de refresh tokens)**

```csharp
// Infrastructure/Persistence/Entities/RefreshTokenEntity.cs
namespace MotorAudiencia.Infrastructure.Persistence.Entities;

[Table("refresh_tokens")]
public sealed class RefreshTokenEntity
{
    [Key] public Guid Id { get; init; } = Guid.NewGuid();
    public string Token { get; init; } = string.Empty;
    public Guid FamilyId { get; init; }
    public Guid UserId { get; init; }
    public DateTime ExpiresAt { get; init; }
    public DateTime CreatedAt { get; init; } = DateTime.UtcNow;
    public bool IsRevoked { get; set; }

    public bool IsExpired => DateTime.UtcNow > ExpiresAt;
    public bool IsActive => !IsRevoked && !IsExpired;
}
```

- [ ] **Step 2: Criar AppDbContext**

```csharp
// Infrastructure/Persistence/AppDbContext.cs
namespace MotorAudiencia.Infrastructure.Persistence;

public sealed class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<User> Users => Set<User>();
    public DbSet<Lead> Leads => Set<Lead>();
    public DbSet<RefreshTokenEntity> RefreshTokens => Set<RefreshTokenEntity>();

    protected override void OnModelCreating(ModelBuilder builder)
    {
        builder.ApplyConfigurationsFromAssembly(typeof(AppDbContext).Assembly);
        base.OnModelCreating(builder);
    }
}
```

- [ ] **Step 3: Criar UserConfiguration**

```csharp
// Infrastructure/Persistence/Configurations/UserConfiguration.cs
namespace MotorAudiencia.Infrastructure.Persistence.Configurations;

public sealed class UserConfiguration : IEntityTypeConfiguration<User>
{
    public void Configure(EntityTypeBuilder<User> builder)
    {
        builder.ToTable("users");
        builder.HasKey(u => u.Id);
        builder.Property(u => u.Username).HasMaxLength(100).IsRequired();
        builder.HasIndex(u => u.Username).IsUnique();
        builder.Property(u => u.PasswordHash).IsRequired();

        builder.HasMany(u => u.RefreshTokens)
               .WithOne()
               .HasForeignKey(r => r.UserId)
               .OnDelete(DeleteBehavior.Cascade);
    }
}
```

- [ ] **Step 4: Criar UserRepository**

```csharp
// Infrastructure/Persistence/Repositories/UserRepository.cs
namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class UserRepository(AppDbContext db) : IUserRepository
{
    public Task<User?> FindByUsernameAsync(string username, CancellationToken ct = default)
        => db.Users
             .Include(u => u.RefreshTokens)
             .FirstOrDefaultAsync(u => u.Username == username.ToLowerInvariant(), ct);

    public Task<User?> FindByRefreshTokenAsync(string token, CancellationToken ct = default)
        => db.Users
             .Include(u => u.RefreshTokens)
             .FirstOrDefaultAsync(u => u.RefreshTokens.Any(r => r.Token == token), ct);

    public async Task SaveAsync(User user, CancellationToken ct = default)
    {
        if (db.Entry(user).State == EntityState.Detached)
            db.Users.Add(user);
        await db.SaveChangesAsync(ct);
    }
}
```

- [ ] **Step 5: Criar migration**

```bash
cd api
dotnet ef migrations add InitialCreate \
  --project src/MotorAudiencia.Infrastructure \
  --startup-project src/MotorAudiencia.API \
  --output-dir Persistence/Migrations
# Esperado: Done. Migration 'InitialCreate' created.
```

- [ ] **Step 6: Commit**

```bash
git add api/src/MotorAudiencia.Infrastructure/Persistence/
git commit -m "feat(persistence): EF Core AppDbContext + UserRepository + migration inicial"
```

---

## Task 6: Use Cases de autenticação

**Files:**
- Create: `api/src/MotorAudiencia.Application/DTOs/LoginRequest.cs`
- Create: `api/src/MotorAudiencia.Application/DTOs/LoginResponse.cs`
- Create: `api/src/MotorAudiencia.Application/Validators/LoginRequestValidator.cs`
- Create: `api/src/MotorAudiencia.Application/UseCases/Auth/LoginUseCase.cs`
- Create: `api/src/MotorAudiencia.Application/UseCases/Auth/RefreshTokenUseCase.cs`
- Create: `api/tests/MotorAudiencia.Tests/UseCases/LoginUseCaseTests.cs`

- [ ] **Step 1: Criar DTOs**

```csharp
// Application/DTOs/LoginRequest.cs
namespace MotorAudiencia.Application.DTOs;

public sealed record LoginRequest(string Username, string Password);
```

```csharp
// Application/DTOs/LoginResponse.cs
namespace MotorAudiencia.Application.DTOs;

public sealed record LoginResponse(string AccessToken, DateTime ExpiresAt);
```

- [ ] **Step 2: Criar validator**

```csharp
// Application/Validators/LoginRequestValidator.cs
namespace MotorAudiencia.Application.Validators;

public sealed class LoginRequestValidator : AbstractValidator<LoginRequest>
{
    public LoginRequestValidator()
    {
        RuleFor(x => x.Username).NotEmpty().MaximumLength(100);
        RuleFor(x => x.Password).NotEmpty().MinimumLength(8);
    }
}
```

- [ ] **Step 3: Escrever testes do LoginUseCase (TDD)**

```csharp
// tests/MotorAudiencia.Tests/UseCases/LoginUseCaseTests.cs
namespace MotorAudiencia.Tests.UseCases;

public class LoginUseCaseTests
{
    private readonly Mock<IUserRepository> _repo = new();
    private readonly Mock<IPasswordHasher> _hasher = new();
    private readonly Mock<IJwtService> _jwt = new();
    private readonly LoginUseCase _sut;

    public LoginUseCaseTests()
        => _sut = new LoginUseCase(_repo.Object, _hasher.Object, _jwt.Object);

    [Fact]
    public async Task Execute_ValidCredentials_ReturnsTokens()
    {
        var user = User.Create("admin", "hash");
        _repo.Setup(r => r.FindByUsernameAsync("admin", default)).ReturnsAsync(user);
        _hasher.Setup(h => h.Verify("senha", "hash")).Returns(true);
        _jwt.Setup(j => j.GenerateAccessToken(user)).Returns("access-token");
        _jwt.Setup(j => j.GenerateRefreshToken(It.IsAny<Guid>())).Returns(new RefreshTokenEntity
            { Token = "refresh-token", ExpiresAt = DateTime.UtcNow.AddDays(7) });

        var result = await _sut.ExecuteAsync(new LoginRequest("admin", "senha"));

        result.IsSuccess.Should().BeTrue();
        result.Value.AccessToken.Should().Be("access-token");
    }

    [Fact]
    public async Task Execute_UserNotFound_ReturnsFailure()
    {
        _repo.Setup(r => r.FindByUsernameAsync(It.IsAny<string>(), default)).ReturnsAsync((User?)null);

        var result = await _sut.ExecuteAsync(new LoginRequest("naoexiste", "senha"));

        result.IsSuccess.Should().BeFalse();
        result.Error.Should().Be("invalid_credentials");
    }

    [Fact]
    public async Task Execute_WrongPassword_ReturnsFailure()
    {
        var user = User.Create("admin", "hash");
        _repo.Setup(r => r.FindByUsernameAsync("admin", default)).ReturnsAsync(user);
        _hasher.Setup(h => h.Verify("errada", "hash")).Returns(false);

        var result = await _sut.ExecuteAsync(new LoginRequest("admin", "errada"));

        result.IsSuccess.Should().BeFalse();
        result.Error.Should().Be("invalid_credentials");
    }
}
```

- [ ] **Step 4: Rodar testes — verificar que falham**

```bash
cd api && dotnet test tests/MotorAudiencia.Tests --filter "FullyQualifiedName~LoginUseCase"
# Esperado: FAIL — LoginUseCase não existe ainda
```

- [ ] **Step 5: Criar Result type simples**

```csharp
// Domain/Result.cs
namespace MotorAudiencia.Domain;

public sealed class Result<T>
{
    public bool IsSuccess { get; }
    public T? Value { get; }
    public string? Error { get; }

    private Result(bool success, T? value, string? error)
        => (IsSuccess, Value, Error) = (success, value, error);

    public static Result<T> Ok(T value) => new(true, value, null);
    public static Result<T> Fail(string error) => new(false, default, error);
}
```

- [ ] **Step 6: Implementar LoginUseCase**

```csharp
// Application/UseCases/Auth/LoginUseCase.cs
namespace MotorAudiencia.Application.UseCases.Auth;

public sealed class LoginUseCase(IUserRepository repo, IPasswordHasher hasher, IJwtService jwt)
{
    public async Task<Result<(string AccessToken, RefreshTokenEntity RefreshToken)>> ExecuteAsync(
        LoginRequest req, CancellationToken ct = default)
    {
        var user = await repo.FindByUsernameAsync(req.Username, ct);
        if (user is null || !hasher.Verify(req.Password, user.PasswordHash))
            return Result<(string, RefreshTokenEntity)>.Fail("invalid_credentials");

        var familyId = Guid.NewGuid();
        var accessToken = jwt.GenerateAccessToken(user);
        var refreshToken = jwt.GenerateRefreshToken(familyId);
        refreshToken.UserId = user.Id;

        user.RefreshTokens.Add(refreshToken);
        await repo.SaveAsync(user, ct);

        return Result<(string, RefreshTokenEntity)>.Ok((accessToken, refreshToken));
    }
}
```

- [ ] **Step 7: Rodar testes — verificar que passam**

```bash
cd api && dotnet test tests/MotorAudiencia.Tests --filter "FullyQualifiedName~LoginUseCase"
# Esperado: 3 passed
```

- [ ] **Step 8: Implementar RefreshTokenUseCase**

```csharp
// Application/UseCases/Auth/RefreshTokenUseCase.cs
namespace MotorAudiencia.Application.UseCases.Auth;

public sealed class RefreshTokenUseCase(IUserRepository repo, IJwtService jwt)
{
    public async Task<Result<(string AccessToken, RefreshTokenEntity NewRefresh)>> ExecuteAsync(
        string token, CancellationToken ct = default)
    {
        var user = await repo.FindByRefreshTokenAsync(token, ct);
        if (user is null) return Result<(string, RefreshTokenEntity)>.Fail("invalid_token");

        var existing = user.RefreshTokens.FirstOrDefault(r => r.Token == token);
        if (existing is null || !existing.IsActive)
        {
            // token inativo ou inválido — revogar toda a família (possível roubo)
            if (existing is not null)
            {
                foreach (var t in user.RefreshTokens.Where(r => r.FamilyId == existing.FamilyId))
                    t.IsRevoked = true;
                await repo.SaveAsync(user, ct);
            }
            return Result<(string, RefreshTokenEntity)>.Fail("token_reuse_detected");
        }

        existing.IsRevoked = true;
        var newRefresh = jwt.GenerateRefreshToken(existing.FamilyId);
        newRefresh.UserId = user.Id;
        user.RefreshTokens.Add(newRefresh);
        await repo.SaveAsync(user, ct);

        return Result<(string, RefreshTokenEntity)>.Ok((jwt.GenerateAccessToken(user), newRefresh));
    }
}
```

- [ ] **Step 9: Commit**

```bash
git add api/src/MotorAudiencia.Application/ api/tests/
git commit -m "feat(auth): LoginUseCase + RefreshTokenUseCase com rotation family"
```

---

## Task 7: AuthController + middlewares de segurança

**Files:**
- Create: `api/src/MotorAudiencia.API/Controllers/AuthController.cs`
- Create: `api/src/MotorAudiencia.API/Middleware/SecurityHeadersMiddleware.cs`
- Create: `api/src/MotorAudiencia.API/Middleware/HmacAuthMiddleware.cs`
- Modify: `api/src/MotorAudiencia.API/Program.cs`

- [ ] **Step 1: Criar SecurityHeadersMiddleware**

```csharp
// API/Middleware/SecurityHeadersMiddleware.cs
namespace MotorAudiencia.API.Middleware;

public sealed class SecurityHeadersMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext ctx)
    {
        var headers = ctx.Response.Headers;
        headers["X-Frame-Options"] = "DENY";
        headers["X-Content-Type-Options"] = "nosniff";
        headers["Referrer-Policy"] = "no-referrer";
        headers["Permissions-Policy"] = "geolocation=(), camera=()";
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains";
        headers["Content-Security-Policy"] = "default-src 'self'";
        await next(ctx);
    }
}
```

- [ ] **Step 2: Criar HmacAuthMiddleware**

```csharp
// API/Middleware/HmacAuthMiddleware.cs
namespace MotorAudiencia.API.Middleware;

public sealed class HmacAuthMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext ctx, HmacValidator validator)
    {
        if (ctx.Request.Path.StartsWithSegments("/internal"))
        {
            var timestamp = ctx.Request.Headers["X-Service-Timestamp"].FirstOrDefault() ?? "";
            var signature = ctx.Request.Headers["X-Service-Signature"].FirstOrDefault() ?? "";
            ctx.Request.EnableBuffering();
            using var reader = new StreamReader(ctx.Request.Body, leaveOpen: true);
            var body = await reader.ReadToEndAsync();
            ctx.Request.Body.Position = 0;

            if (!validator.IsValid(timestamp, body, signature))
            {
                ctx.Response.StatusCode = 401;
                await ctx.Response.WriteAsync("unauthorized");
                return;
            }
        }
        await next(ctx);
    }
}
```

- [ ] **Step 3: Criar AuthController**

```csharp
// API/Controllers/AuthController.cs
namespace MotorAudiencia.API.Controllers;

[ApiController]
[Route("auth")]
public sealed class AuthController(LoginUseCase login, RefreshTokenUseCase refresh) : ControllerBase
{
    [HttpPost("login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest req, CancellationToken ct)
    {
        var result = await login.ExecuteAsync(req, ct);
        if (!result.IsSuccess)
            return Unauthorized(new { error = result.Error });

        var (accessToken, refreshToken) = result.Value;
        Response.Cookies.Append("refresh_token", refreshToken.Token, new CookieOptions
        {
            HttpOnly = true,
            Secure = true,
            SameSite = SameSiteMode.Strict,
            Expires = refreshToken.ExpiresAt,
        });
        return Ok(new { accessToken, expiresAt = DateTime.UtcNow.AddMinutes(15) });
    }

    [HttpPost("refresh")]
    public async Task<IActionResult> Refresh(CancellationToken ct)
    {
        var token = Request.Cookies["refresh_token"];
        if (string.IsNullOrEmpty(token)) return Unauthorized();

        var result = await refresh.ExecuteAsync(token, ct);
        if (!result.IsSuccess) return Unauthorized(new { error = result.Error });

        var (accessToken, newRefresh) = result.Value;
        Response.Cookies.Append("refresh_token", newRefresh.Token, new CookieOptions
        {
            HttpOnly = true, Secure = true, SameSite = SameSiteMode.Strict,
            Expires = newRefresh.ExpiresAt,
        });
        return Ok(new { accessToken, expiresAt = DateTime.UtcNow.AddMinutes(15) });
    }

    [HttpPost("logout")]
    [Authorize]
    public IActionResult Logout()
    {
        Response.Cookies.Delete("refresh_token");
        return NoContent();
    }

    [HttpGet("me")]
    [Authorize]
    public IActionResult Me()
        => Ok(new { username = User.Identity?.Name });
}
```

- [ ] **Step 4: Configurar Program.cs completo**

```csharp
// API/Program.cs
var builder = WebApplication.CreateBuilder(args);

// Logging
builder.Host.UseSerilog((ctx, cfg) => cfg
    .ReadFrom.Configuration(ctx.Configuration)
    .WriteTo.Console(new JsonFormatter()));

// Options com validação — falha no startup se ausentes
builder.Services.AddOptions<JwtOptions>()
    .Bind(builder.Configuration.GetSection(JwtOptions.Section))
    .ValidateDataAnnotations().ValidateOnStart();
builder.Services.AddOptions<SecurityOptions>()
    .Bind(builder.Configuration.GetSection(SecurityOptions.Section))
    .ValidateDataAnnotations().ValidateOnStart();

// Database
builder.Services.AddDbContext<AppDbContext>(opt =>
    opt.UseNpgsql(builder.Configuration["DATABASE_URL"]));

// Auth
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(opt =>
    {
        var jwtSection = builder.Configuration.GetSection(JwtOptions.Section);
        opt.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(jwtSection["Secret"]!)),
            ValidateIssuer = true, ValidIssuer = jwtSection["Issuer"],
            ValidateAudience = true, ValidAudience = jwtSection["Audience"],
            ClockSkew = TimeSpan.Zero,
        };
    });
builder.Services.AddAuthorization();

// Rate Limiting
builder.Services.AddRateLimiter(opt =>
{
    opt.AddSlidingWindowLimiter("global", lim =>
    {
        lim.PermitLimit = 100; lim.Window = TimeSpan.FromMinutes(1);
        lim.SegmentsPerWindow = 6;
    });
    opt.AddSlidingWindowLimiter("login", lim =>
    {
        lim.PermitLimit = 10; lim.Window = TimeSpan.FromMinutes(1);
        lim.SegmentsPerWindow = 2;
    });
    opt.RejectionStatusCode = 429;
});

// CORS
builder.Services.AddCors(opt => opt.AddDefaultPolicy(p =>
    p.WithOrigins(builder.Configuration["CORS_ORIGIN"] ?? "http://localhost:3000")
     .AllowAnyMethod().AllowAnyHeader().AllowCredentials()));

// DI
builder.Services.AddScoped<IPasswordHasher, Argon2idPasswordHasher>();
builder.Services.AddScoped<IJwtService, JwtService>();
builder.Services.AddScoped<IUserRepository, UserRepository>();
builder.Services.AddScoped<HmacValidator>();
builder.Services.AddScoped<LoginUseCase>();
builder.Services.AddScoped<RefreshTokenUseCase>();
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Middleware pipeline (ordem importa)
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<HmacAuthMiddleware>();
app.UseSerilogRequestLogging();
app.UseCors();
app.UseRateLimiter();
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();

if (app.Environment.IsDevelopment())
    app.UseSwagger().UseSwaggerUI();

// Migrations + seed
await using (var scope = app.Services.CreateAsyncScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    await db.Database.MigrateAsync();
    await DatabaseSeeder.SeedAsync(scope.ServiceProvider);
}

app.Run();
```

- [ ] **Step 5: Commit**

```bash
git add api/src/MotorAudiencia.API/
git commit -m "feat(api): AuthController + SecurityHeaders + HMAC middleware + Program.cs"
```

---

## Task 8: Seed do usuário admin

**Files:**
- Create: `api/src/MotorAudiencia.API/Startup/DatabaseSeeder.cs`

- [ ] **Step 1: Implementar DatabaseSeeder**

```csharp
// API/Startup/DatabaseSeeder.cs
namespace MotorAudiencia.API.Startup;

public static class DatabaseSeeder
{
    public static async Task SeedAsync(IServiceProvider services)
    {
        var config = services.GetRequiredService<IConfiguration>();
        var username = config["ADMIN_USERNAME"] ?? "admin";
        var password = config["ADMIN_PASSWORD"]
            ?? throw new InvalidOperationException("ADMIN_PASSWORD não configurado.");

        var repo = services.GetRequiredService<IUserRepository>();
        var hasher = services.GetRequiredService<IPasswordHasher>();
        var logger = services.GetRequiredService<ILogger<DatabaseSeeder>>();

        var existing = await repo.FindByUsernameAsync(username);
        if (existing is not null)
        {
            logger.LogInformation("Admin já existe, seed ignorado.");
            return;
        }

        var user = User.Create(username, hasher.Hash(password));
        await repo.SaveAsync(user);
        logger.LogInformation("Admin seedado com sucesso.");
    }
}
```

- [ ] **Step 2: Criar Dockerfile**

```dockerfile
# api/Dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS base
WORKDIR /app
EXPOSE 5000

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ["src/MotorAudiencia.API/MotorAudiencia.API.csproj", "src/MotorAudiencia.API/"]
COPY ["src/MotorAudiencia.Application/MotorAudiencia.Application.csproj", "src/MotorAudiencia.Application/"]
COPY ["src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj", "src/MotorAudiencia.Infrastructure/"]
COPY ["src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj", "src/MotorAudiencia.Domain/"]
RUN dotnet restore "src/MotorAudiencia.API/MotorAudiencia.API.csproj"
COPY . .
RUN dotnet publish "src/MotorAudiencia.API/MotorAudiencia.API.csproj" -c Release -o /app/publish

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "MotorAudiencia.API.dll"]
```

- [ ] **Step 3: Rodar todos os testes**

```bash
cd api && dotnet test
# Esperado: 7+ passed, 0 failed
```

- [ ] **Step 4: Subir infra e testar login**

```bash
# Copiar .env.example para .env e preencher valores mínimos:
# JWT_SECRET=<64+ chars>
# AUTH_PEPPER=<32+ chars>
# SERVICE_SECRET=<32+ chars>
# ADMIN_USERNAME=admin
# ADMIN_PASSWORD=<senha forte>
# POSTGRES_PASSWORD=<qualquer>

cd infra && docker compose up -d postgres rabbitmq
cd api && dotnet run --project src/MotorAudiencia.API

# Testar login
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}' \
  -c cookies.txt

# Esperado: {"accessToken":"eyJ...","expiresAt":"..."}

# Testar /me com token
curl http://localhost:5000/auth/me \
  -H "Authorization: Bearer <accessToken>"
# Esperado: {"username":"admin"}
```

- [ ] **Step 5: Commit final da fase**

```bash
git add api/
git commit -m "feat(seed): DatabaseSeeder + Dockerfile + Fase 1 completa"
```

---

## Checklist de conclusão da Fase 1

- [ ] `docker compose up -d` sobe postgres + rabbitmq sem erros
- [ ] `dotnet build` retorna 0 erros
- [ ] `dotnet test` retorna 7+ passed, 0 failed
- [ ] `POST /auth/login` retorna JWT válido
- [ ] `POST /auth/refresh` rotaciona refresh token
- [ ] `GET /auth/me` com token expirado retorna 401
- [ ] Headers de segurança presentes em toda resposta
- [ ] Rota `/internal/*` sem HMAC retorna 401
- [ ] Seed do admin idempotente (segunda execução não cria duplicata)

---

## Próximas fases

- **Fase 2** — Workers .NET: ValidatorWorker, DeduplicatorWorker, EnricherWorker, ScorerWorker + MassTransit
- **Fase 3** — Node.js Services: Tagger, Orchestrator, Scraper, Notification, Outreach
- **Fase 4** — Next.js 14: auth flow, dashboard, leads, campanhas, pesquisa
- **Fase 5** — Sweep + SignalR + integração E2E
