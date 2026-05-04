using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface IScoreRepository
{
    Task SaveAsync(Score score, CancellationToken ct = default);
    Task<Score?> FindByLeadIdAsync(Guid leadId, CancellationToken ct = default);
}
