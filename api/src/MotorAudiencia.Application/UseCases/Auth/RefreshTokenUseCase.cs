using MotorAudiencia.Application.DTOs;
using MotorAudiencia.Domain;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Application.UseCases.Auth;

public sealed class RefreshTokenUseCase(
    IUserRepository repo,
    IJwtService jwt,
    IRefreshTokenRepository tokens)
{
    public async Task<Result<(string AccessToken, string RefreshToken, DateTime RefreshExpiresAt)>> ExecuteAsync(
        string token, CancellationToken ct = default)
    {
        var existing = await tokens.FindByTokenAsync(token, ct);
        if (existing is null)
            return Result<(string, string, DateTime)>.Fail("invalid_token");

        if (!existing.IsActive)
        {
            if (existing.IsRevoked)
                await tokens.RevokeAllByFamilyAsync(existing.FamilyId, ct);
            return Result<(string, string, DateTime)>.Fail(
                existing.IsRevoked ? "token_reuse_detected" : "token_expired");
        }

        var user = await repo.FindByRefreshTokenAsync(token, ct);
        if (user is null)
            return Result<(string, string, DateTime)>.Fail("invalid_token");

        await tokens.RevokeAsync(token, ct);
        var newRefresh = jwt.GenerateRefreshToken(user.Id);
        await tokens.AddAsync(newRefresh, ct);

        return Result<(string, string, DateTime)>.Ok((
            jwt.GenerateAccessToken(user),
            newRefresh.Token,
            newRefresh.ExpiresAt));
    }
}
