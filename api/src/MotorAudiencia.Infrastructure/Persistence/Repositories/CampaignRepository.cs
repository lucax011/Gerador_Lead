using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class CampaignRepository(AppDbContext db) : ICampaignRepository
{
    public Task<Campaign?> FindByIdAsync(Guid id, CancellationToken ct = default)
        => db.Campaigns.FirstOrDefaultAsync(c => c.Id == id, ct);
}
