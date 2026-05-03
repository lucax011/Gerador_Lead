using Microsoft.Extensions.Logging;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;

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
        var loggerFactory = services.GetRequiredService<ILoggerFactory>();
        var logger = loggerFactory.CreateLogger(nameof(DatabaseSeeder));

        var existing = await repo.FindByUsernameAsync(username);
        if (existing is not null)
        {
            logger.LogInformation("Admin '{Username}' já existe, seed ignorado.", username);
            return;
        }

        var user = User.Create(username, hasher.Hash(password));
        await repo.SaveAsync(user);
        logger.LogInformation("Admin '{Username}' seedado com sucesso.", username);
    }
}
