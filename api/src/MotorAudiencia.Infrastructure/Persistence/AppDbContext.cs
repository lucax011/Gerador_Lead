using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Infrastructure.Persistence.Entities;

namespace MotorAudiencia.Infrastructure.Persistence;

public sealed class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<User> Users => Set<User>();
    public DbSet<RefreshTokenEntity> RefreshTokens => Set<RefreshTokenEntity>();
    public DbSet<Lead> Leads => Set<Lead>();
    public DbSet<Source> Sources => Set<Source>();
    public DbSet<Niche> Niches => Set<Niche>();
    public DbSet<Score> Scores => Set<Score>();

    protected override void OnModelCreating(ModelBuilder builder)
    {
        builder.ApplyConfigurationsFromAssembly(typeof(AppDbContext).Assembly);
        base.OnModelCreating(builder);
    }
}
