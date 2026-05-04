using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface ILeadRepository
{
    Task<Lead?> FindByIdAsync(Guid id, CancellationToken ct = default);
    Task<Lead?> FindByEmailAsync(string email, CancellationToken ct = default);
    Task SaveAsync(Lead lead, CancellationToken ct = default);
}
