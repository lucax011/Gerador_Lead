using System.Text;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using MotorAudiencia.API.Middleware;
using MotorAudiencia.API.Startup;
using MotorAudiencia.Application.Options;
using MotorAudiencia.Application.UseCases.Auth;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.Persistence;
using MotorAudiencia.Infrastructure.Persistence.Repositories;
using MotorAudiencia.Infrastructure.Security;
using Serilog;
using Serilog.Formatting.Json;

var builder = WebApplication.CreateBuilder(args);

// Logging
builder.Host.UseSerilog((ctx, cfg) => cfg
    .ReadFrom.Configuration(ctx.Configuration)
    .WriteTo.Console(new JsonFormatter()));

// Options with startup validation
builder.Services.AddOptions<JwtOptions>()
    .Bind(builder.Configuration.GetSection(JwtOptions.Section))
    .ValidateDataAnnotations().ValidateOnStart();
builder.Services.AddOptions<SecurityOptions>()
    .Bind(builder.Configuration.GetSection(SecurityOptions.Section))
    .ValidateDataAnnotations().ValidateOnStart();

// Database
builder.Services.AddDbContext<AppDbContext>(opt =>
    opt.UseNpgsql(builder.Configuration["DATABASE_URL"]));

// JWT Authentication
var jwtSection = builder.Configuration.GetSection(JwtOptions.Section);
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(opt => opt.TokenValidationParameters = new TokenValidationParameters
    {
        ValidateIssuerSigningKey = true,
        IssuerSigningKey = new SymmetricSecurityKey(
            Encoding.UTF8.GetBytes(jwtSection["Secret"] ?? "")),
        ValidateIssuer = true, ValidIssuer = jwtSection["Issuer"],
        ValidateAudience = true, ValidAudience = jwtSection["Audience"],
        ClockSkew = TimeSpan.Zero,
    });
builder.Services.AddAuthorization();

// Rate Limiting
builder.Services.AddRateLimiter(opt =>
{
    opt.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(ctx =>
        RateLimitPartition.GetSlidingWindowLimiter(
            ctx.Connection.RemoteIpAddress?.ToString() ?? "anon",
            _ => new SlidingWindowRateLimiterOptions
            {
                PermitLimit = 100,
                Window = TimeSpan.FromMinutes(1),
                SegmentsPerWindow = 6,
                QueueProcessingOrder = QueueProcessingOrder.OldestFirst,
                QueueLimit = 0,
            }));

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
builder.Services.AddScoped<IRefreshTokenRepository, RefreshTokenRepository>();
builder.Services.AddScoped<IHmacValidator, HmacValidator>();
builder.Services.AddScoped<LoginUseCase>();
builder.Services.AddScoped<RefreshTokenUseCase>();
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Middleware pipeline (order matters)
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

// Migrations + seed on startup
await using (var scope = app.Services.CreateAsyncScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    await db.Database.MigrateAsync();
    await DatabaseSeeder.SeedAsync(scope.ServiceProvider);
}

app.Run();

public partial class Program { }
