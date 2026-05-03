// Domain/Interfaces/IUserRepository.cs
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface IUserRepository
{
    Task<User?> FindByUsernameAsync(string username, CancellationToken ct = default);
    Task<User?> FindByRefreshTokenAsync(string token, CancellationToken ct = default);
    Task SaveAsync(User user, CancellationToken ct = default);
}
