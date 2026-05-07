using MassTransit;
using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.AI;
using MotorAudiencia.Infrastructure.Messaging.Consumers;
using MotorAudiencia.Infrastructure.Persistence;
using MotorAudiencia.Infrastructure.Persistence.Repositories;
using Serilog;
using Serilog.Formatting.Json;

Log.Logger = new LoggerConfiguration()
    .WriteTo.Console(new JsonFormatter())
    .CreateBootstrapLogger();

try
{
    var host = Host.CreateDefaultBuilder(args)
        .UseSerilog((_, cfg) => cfg
            .MinimumLevel.Information()
            .WriteTo.Console(new JsonFormatter()))
        .ConfigureServices((ctx, services) =>
        {
            var dbUrl = ctx.Configuration["DATABASE_URL"]
                ?? throw new InvalidOperationException("DATABASE_URL não configurado.");
            var rabbitUrl = ctx.Configuration["RABBITMQ_URL"]
                ?? throw new InvalidOperationException("RABBITMQ_URL não configurado.");

            services.AddDbContext<AppDbContext>(opt => opt.UseNpgsql(dbUrl));
            services.AddScoped<ILeadRepository, LeadRepository>();
            services.AddScoped<IScoreRepository, ScoreRepository>();
            services.AddScoped<ICampaignRepository, CampaignRepository>();

            var openAiKey = ctx.Configuration["OPENAI_API_KEY"];
            if (!string.IsNullOrEmpty(openAiKey))
            {
                services.AddHttpClient("openai", http =>
                {
                    http.BaseAddress = new Uri("https://api.openai.com/");
                    http.Timeout = TimeSpan.FromSeconds(30);
                });
                services.AddScoped<IOrchestratorAiClient, OpenAiOrchestratorClient>();
            }
            else
            {
                Log.Warning("OPENAI_API_KEY ausente — usando fallback determinístico");
                services.AddScoped<IOrchestratorAiClient, DeterministicOrchestratorClient>();
            }

            services.AddMassTransit(x =>
            {
                x.AddConsumer<OrchestratorConsumer>();

                x.UsingRabbitMq((mctx, cfg) =>
                {
                    cfg.Host(rabbitUrl);

                    cfg.UseMessageRetry(r => r.Intervals(
                        TimeSpan.FromSeconds(5),
                        TimeSpan.FromSeconds(15),
                        TimeSpan.FromSeconds(30)));

                    cfg.ReceiveEndpoint("ma-orchestrator", e =>
                    {
                        e.PrefetchCount = 5;
                        e.ConfigureConsumer<OrchestratorConsumer>(mctx);
                    });
                });
            });
        })
        .Build();

    await host.RunAsync();
}
catch (Exception ex)
{
    Log.Fatal(ex, "OrchestratorWorker encerrado com erro");
}
finally
{
    await Log.CloseAndFlushAsync();
}
