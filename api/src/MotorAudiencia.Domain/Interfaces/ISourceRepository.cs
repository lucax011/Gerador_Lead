using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface ISourceRepository
{
    Task<Source?> FindByIdAsync(Guid id, CancellationToken ct = default);
    Task<Source?> FindByNameAsync(string name, CancellationToken ct = default);
}
