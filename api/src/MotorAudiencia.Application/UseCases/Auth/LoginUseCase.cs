using MotorAudiencia.Application.DTOs;
using MotorAudiencia.Domain;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Application.UseCases.Auth;

public sealed class LoginUseCase(
    IUserRepository repo,
    IPasswordHasher hasher,
    IJwtService jwt,
    IRefreshTokenRepository tokens)
{
    public async Task<Result<LoginResponse>> ExecuteAsync(LoginRequest req, CancellationToken ct = default)
    {
        var user = await repo.FindByUsernameAsync(req.Username, ct);
        if (user is null || !hasher.Verify(req.Password, user.PasswordHash))
            return Result<LoginResponse>.Fail("invalid_credentials");

        var accessToken = jwt.GenerateAccessToken(user);
        var refreshToken = jwt.GenerateRefreshToken(user.Id);
        await tokens.AddAsync(refreshToken, ct);

        return Result<LoginResponse>.Ok(new LoginResponse(
            accessToken,
            DateTime.UtcNow.AddMinutes(15)));
    }
}
