using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.Persistence;

namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class LeadRepository(AppDbContext db) : ILeadRepository
{
    public Task<Lead?> FindByIdAsync(Guid id, CancellationToken ct = default)
        => db.Leads.FirstOrDefaultAsync(l => l.Id == id, ct);

    public Task<Lead?> FindByEmailAsync(string email, CancellationToken ct = default)
        => db.Leads.FirstOrDefaultAsync(l => l.Email == email.ToLowerInvariant(), ct);

    public async Task SaveAsync(Lead lead, CancellationToken ct = default)
    {
        if (db.Entry(lead).State == EntityState.Detached)
            db.Leads.Add(lead);
        await db.SaveChangesAsync(ct);
    }
}
