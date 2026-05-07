using MassTransit;
using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Interfaces;
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

            services.AddMassTransit(x =>
            {
                x.AddConsumer<DeduplicatorConsumer>();

                x.UsingRabbitMq((mctx, cfg) =>
                {
                    cfg.Host(rabbitUrl);

                    cfg.UseMessageRetry(r => r.Intervals(
                        TimeSpan.FromSeconds(5),
                        TimeSpan.FromSeconds(15),
                        TimeSpan.FromSeconds(30)));

                    cfg.ReceiveEndpoint("ma-deduplicator", e =>
                    {
                        e.PrefetchCount = 10;
                        e.ConfigureConsumer<DeduplicatorConsumer>(mctx);
                    });
                });
            });
        })
        .Build();

    await host.RunAsync();
}
catch (Exception ex)
{
    Log.Fatal(ex, "DeduplicatorWorker encerrado com erro");
}
finally
{
    await Log.CloseAndFlushAsync();
}
