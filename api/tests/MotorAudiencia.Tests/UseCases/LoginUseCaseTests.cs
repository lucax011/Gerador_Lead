using FluentAssertions;
using Moq;
using MotorAudiencia.Application.DTOs;
using MotorAudiencia.Application.UseCases.Auth;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Tests.UseCases;

public class LoginUseCaseTests
{
    private readonly Mock<IUserRepository> _repo = new();
    private readonly Mock<IPasswordHasher> _hasher = new();
    private readonly Mock<IJwtService> _jwt = new();
    private readonly Mock<IRefreshTokenRepository> _tokens = new();
    private readonly LoginUseCase _sut;

    public LoginUseCaseTests()
        => _sut = new LoginUseCase(_repo.Object, _hasher.Object, _jwt.Object, _tokens.Object);

    [Fact]
    public async Task Execute_ValidCredentials_ReturnsTokens()
    {
        var user = User.Create("admin", "hash");
        _repo.Setup(r => r.FindByUsernameAsync("admin", default)).ReturnsAsync(user);
        _hasher.Setup(h => h.Verify("senha", "hash")).Returns(true);
        _jwt.Setup(j => j.GenerateAccessToken(user)).Returns("access-token");
        _jwt.Setup(j => j.GenerateRefreshToken(user.Id))
            .Returns(new RefreshTokenResult("refresh-token", Guid.NewGuid(), user.Id, DateTime.UtcNow.AddDays(7)));

        var result = await _sut.ExecuteAsync(new LoginRequest("admin", "senha"));

        result.IsSuccess.Should().BeTrue();
        result.Value!.AccessToken.Should().Be("access-token");
        result.Value!.RefreshToken.Should().Be("refresh-token");
        result.Value!.RefreshExpiresAt.Should().BeAfter(DateTime.UtcNow);
    }

    [Fact]
    public async Task Execute_UserNotFound_ReturnsFailure()
    {
        _repo.Setup(r => r.FindByUsernameAsync(It.IsAny<string>(), default)).ReturnsAsync((User?)null);

        var result = await _sut.ExecuteAsync(new LoginRequest("naoexiste", "senha12345"));

        result.IsSuccess.Should().BeFalse();
        result.Error.Should().Be("invalid_credentials");
    }

    [Fact]
    public async Task Execute_WrongPassword_ReturnsFailure()
    {
        var user = User.Create("admin", "hash");
        _repo.Setup(r => r.FindByUsernameAsync("admin", default)).ReturnsAsync(user);
        _hasher.Setup(h => h.Verify("errada123", "hash")).Returns(false);

        var result = await _sut.ExecuteAsync(new LoginRequest("admin", "errada123"));

        result.IsSuccess.Should().BeFalse();
        result.Error.Should().Be("invalid_credentials");
    }

    [Fact]
    public async Task Execute_ValidCredentials_SavesRefreshToken()
    {
        var user = User.Create("admin", "hash");
        var refreshResult = new RefreshTokenResult("rt", Guid.NewGuid(), user.Id, DateTime.UtcNow.AddDays(7));
        _repo.Setup(r => r.FindByUsernameAsync("admin", default)).ReturnsAsync(user);
        _hasher.Setup(h => h.Verify("senha123", "hash")).Returns(true);
        _jwt.Setup(j => j.GenerateAccessToken(user)).Returns("tok");
        _jwt.Setup(j => j.GenerateRefreshToken(user.Id)).Returns(refreshResult);

        await _sut.ExecuteAsync(new LoginRequest("admin", "senha123"));

        _tokens.Verify(t => t.AddAsync(refreshResult, default), Times.Once);
    }
}
