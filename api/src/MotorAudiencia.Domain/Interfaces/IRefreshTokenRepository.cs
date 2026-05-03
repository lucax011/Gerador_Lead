namespace MotorAudiencia.Domain.Interfaces;

public interface IRefreshTokenRepository
{
    Task<RefreshTokenInfo?> FindByTokenAsync(string token, CancellationToken ct = default);
    Task AddAsync(RefreshTokenResult token, CancellationToken ct = default);
    Task RevokeAsync(string token, CancellationToken ct = default);
    Task RevokeAllByFamilyAsync(Guid familyId, CancellationToken ct = default);
}
