using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface ICampaignRepository
{
    Task<Campaign?> FindByIdAsync(Guid id, CancellationToken ct = default);
}
