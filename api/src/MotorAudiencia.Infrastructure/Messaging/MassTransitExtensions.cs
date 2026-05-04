using MassTransit;
using Microsoft.Extensions.DependencyInjection;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.Http;
using MotorAudiencia.Infrastructure.Messaging.Consumers;
using MotorAudiencia.Infrastructure.Persistence.Repositories;

namespace MotorAudiencia.Infrastructure.Messaging;

public static class MassTransitExtensions
{
    /// <summary>
    /// Registra MassTransit com os 4 consumers do pipeline + repositórios de lead + CNPJ client.
    /// Usar em Worker Services — não na API.
    /// </summary>
    public static IServiceCollection AddWorkerBus(
        this IServiceCollection services,
        string rabbitMqUrl,
        string cnpjWsBaseUrl = "https://publica.cnpj.ws")
    {
        services.AddHttpClient<ICnpjWsClient, CnpjWsClient>(http =>
        {
            http.BaseAddress = new Uri(cnpjWsBaseUrl);
            http.Timeout = TimeSpan.FromSeconds(10);
            http.DefaultRequestHeaders.Add("User-Agent", "MotorAudiencia/1.0");
        });

        services.AddScoped<ILeadRepository, LeadRepository>();
        services.AddScoped<ISourceRepository, SourceRepository>();
        services.AddScoped<INicheRepository, NicheRepository>();
        services.AddScoped<IScoreRepository, ScoreRepository>();

        services.AddMassTransit(x =>
        {
            x.AddConsumer<ValidatorConsumer>();
            x.AddConsumer<DeduplicatorConsumer>();
            x.AddConsumer<EnricherConsumer>();
            x.AddConsumer<ScorerConsumer>();

            x.UsingRabbitMq((ctx, cfg) =>
            {
                cfg.Host(rabbitMqUrl);

                // Retry: 3 tentativas com backoff 5s → 15s → 30s
                cfg.UseMessageRetry(r =>
                    r.Intervals(
                        TimeSpan.FromSeconds(5),
                        TimeSpan.FromSeconds(15),
                        TimeSpan.FromSeconds(30)));

                cfg.ReceiveEndpoint("ma-validator", e =>
                {
                    e.PrefetchCount = 10;
                    e.ConfigureConsumer<ValidatorConsumer>(ctx);
                });

                cfg.ReceiveEndpoint("ma-deduplicator", e =>
                {
                    e.PrefetchCount = 10;
                    e.ConfigureConsumer<DeduplicatorConsumer>(ctx);
                });

                cfg.ReceiveEndpoint("ma-enricher", e =>
                {
                    e.PrefetchCount = 10;
                    e.ConfigureConsumer<EnricherConsumer>(ctx);
                });

                cfg.ReceiveEndpoint("ma-scorer", e =>
                {
                    e.PrefetchCount = 10;
                    e.ConfigureConsumer<ScorerConsumer>(ctx);
                });
            });
        });

        return services;
    }
}
