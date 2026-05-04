using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.Persistence;

namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class NicheRepository(AppDbContext db) : INicheRepository
{
    public Task<Niche?> FindByIdAsync(Guid id, CancellationToken ct = default)
        => db.Niches.FirstOrDefaultAsync(n => n.Id == id, ct);

    public Task<Niche?> FindByNameAsync(string name, CancellationToken ct = default)
        => db.Niches.FirstOrDefaultAsync(n => n.Name == name.ToLowerInvariant(), ct);
}
