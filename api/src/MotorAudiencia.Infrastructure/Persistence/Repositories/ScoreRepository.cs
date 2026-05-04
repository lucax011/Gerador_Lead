using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.Persistence;

namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class ScoreRepository(AppDbContext db) : IScoreRepository
{
    public async Task SaveAsync(Score score, CancellationToken ct = default)
    {
        if (db.Entry(score).State == EntityState.Detached)
            db.Scores.Add(score);
        await db.SaveChangesAsync(ct);
    }

    public Task<Score?> FindByLeadIdAsync(Guid leadId, CancellationToken ct = default)
        => db.Scores.FirstOrDefaultAsync(s => s.LeadId == leadId, ct);
}
