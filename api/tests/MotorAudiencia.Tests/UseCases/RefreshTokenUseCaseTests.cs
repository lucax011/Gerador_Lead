using FluentAssertions;
using Moq;
using MotorAudiencia.Application.UseCases.Auth;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Tests.UseCases;

public class RefreshTokenUseCaseTests
{
    private readonly Mock<IUserRepository> _repo = new();
    private readonly Mock<IJwtService> _jwt = new();
    private readonly Mock<IRefreshTokenRepository> _tokens = new();
    private readonly RefreshTokenUseCase _sut;

    public RefreshTokenUseCaseTests()
        => _sut = new RefreshTokenUseCase(_repo.Object, _jwt.Object, _tokens.Object);

    [Fact]
    public async Task Execute_ValidToken_ReturnsNewTokens()
    {
        var userId = Guid.NewGuid();
        var familyId = Guid.NewGuid();
        var user = User.Create("admin", "hash");
        var tokenInfo = new RefreshTokenInfo("old-token", familyId, userId, DateTime.UtcNow.AddDays(7), false);
        var newRefresh = new RefreshTokenResult("new-token", familyId, userId, DateTime.UtcNow.AddDays(7));

        _tokens.Setup(t => t.FindByTokenAsync("old-token", default)).ReturnsAsync(tokenInfo);
        _repo.Setup(r => r.FindByUsernameAsync(It.IsAny<string>(), default)).ReturnsAsync((User?)null);
        _repo.Setup(r => r.FindByRefreshTokenAsync("old-token", default)).ReturnsAsync(user);
        _jwt.Setup(j => j.GenerateAccessToken(user)).Returns("new-access");
        _jwt.Setup(j => j.GenerateRefreshToken(It.IsAny<Guid>())).Returns(newRefresh);

        var result = await _sut.ExecuteAsync("old-token");

        result.IsSuccess.Should().BeTrue();
        result.Value!.AccessToken.Should().Be("new-access");
    }

    [Fact]
    public async Task Execute_TokenNotFound_ReturnsFailure()
    {
        _tokens.Setup(t => t.FindByTokenAsync("unknown", default)).ReturnsAsync((RefreshTokenInfo?)null);

        var result = await _sut.ExecuteAsync("unknown");

        result.IsSuccess.Should().BeFalse();
        result.Error.Should().Be("invalid_token");
    }

    [Fact]
    public async Task Execute_RevokedToken_RevokesFamily_ReturnsFailure()
    {
        var familyId = Guid.NewGuid();
        var tokenInfo = new RefreshTokenInfo("revoked-token", familyId, Guid.NewGuid(), DateTime.UtcNow.AddDays(7), true);
        _tokens.Setup(t => t.FindByTokenAsync("revoked-token", default)).ReturnsAsync(tokenInfo);

        var result = await _sut.ExecuteAsync("revoked-token");

        _tokens.Verify(t => t.RevokeAllByFamilyAsync(familyId, default), Times.Once);
        result.IsSuccess.Should().BeFalse();
        result.Error.Should().Be("token_reuse_detected");
    }

    [Fact]
    public async Task Execute_ExpiredToken_ReturnsFailure()
    {
        var tokenInfo = new RefreshTokenInfo("expired-token", Guid.NewGuid(), Guid.NewGuid(), DateTime.UtcNow.AddDays(-1), false);
        _tokens.Setup(t => t.FindByTokenAsync("expired-token", default)).ReturnsAsync(tokenInfo);

        var result = await _sut.ExecuteAsync("expired-token");

        result.IsSuccess.Should().BeFalse();
        result.Error.Should().Be("token_expired");
    }
}
