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
    // Constant dummy hash — always call Verify to normalize timing
    // Salt is valid base64(16 bytes), hash is valid base64(32 bytes)
    private const string DummyHash = "AAAAAAAAAAAAAAAAAAAAAA==:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==";

    public async Task<Result<LoginResponse>> ExecuteAsync(LoginRequest req, CancellationToken ct = default)
    {
        var user = await repo.FindByUsernameAsync(req.Username, ct);
        var hashToVerify = user?.PasswordHash ?? DummyHash;
        var credentialsValid = user is not null && hasher.Verify(req.Password, hashToVerify);
        if (!credentialsValid)
            return Result<LoginResponse>.Fail("invalid_credentials");

        var accessToken = jwt.GenerateAccessToken(user!);
        var refreshToken = jwt.GenerateRefreshToken(user!.Id);
        await tokens.AddAsync(refreshToken, ct);

        return Result<LoginResponse>.Ok(new LoginResponse(
            accessToken,
            DateTime.UtcNow.AddMinutes(15),
            refreshToken.Token,
            refreshToken.ExpiresAt));
    }
}
