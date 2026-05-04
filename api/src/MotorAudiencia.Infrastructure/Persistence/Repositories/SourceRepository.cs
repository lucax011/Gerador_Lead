using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.Persistence;

namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class SourceRepository(AppDbContext db) : ISourceRepository
{
    public Task<Source?> FindByIdAsync(Guid id, CancellationToken ct = default)
        => db.Sources.FirstOrDefaultAsync(s => s.Id == id, ct);

    public Task<Source?> FindByNameAsync(string name, CancellationToken ct = default)
        => db.Sources.FirstOrDefaultAsync(s => s.Name == name.ToLowerInvariant(), ct);
}
