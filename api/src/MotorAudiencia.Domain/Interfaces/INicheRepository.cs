using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface INicheRepository
{
    Task<Niche?> FindByIdAsync(Guid id, CancellationToken ct = default);
    Task<Niche?> FindByNameAsync(string name, CancellationToken ct = default);
}
