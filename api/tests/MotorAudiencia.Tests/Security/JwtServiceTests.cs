using FluentAssertions;
using Microsoft.Extensions.Options;
using MotorAudiencia.Application.Options;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Infrastructure.Security;

namespace MotorAudiencia.Tests.Security;

public class JwtServiceTests
{
    private readonly JwtService _sut;
    private readonly JwtOptions _opts = new()
    {
        Secret = "test-secret-must-be-at-least-64-chars-long-for-hmac-sha256-ok!!",
        Issuer = "test-issuer",
        Audience = "test-audience",
        AccessTokenMinutes = 15,
        RefreshTokenDays = 7,
    };

    public JwtServiceTests() => _sut = new JwtService(Options.Create(_opts));

    [Fact]
    public void GenerateAccessToken_ReturnsNonEmptyJwt()
    {
        var user = User.Create("admin", "hash");
        _sut.GenerateAccessToken(user).Should().NotBeNullOrEmpty().And.Contain(".");
    }

    [Fact]
    public void ValidateAccessToken_ValidToken_ReturnsUserId()
    {
        var user = User.Create("admin", "hash");
        var token = _sut.GenerateAccessToken(user);
        _sut.ValidateAccessToken(token).Should().Be(user.Id);
    }

    [Fact]
    public void ValidateAccessToken_InvalidToken_ReturnsNull()
    {
        _sut.ValidateAccessToken("not.a.token").Should().BeNull();
    }

    [Fact]
    public void GenerateRefreshToken_ReturnsValidResult()
    {
        var userId = Guid.NewGuid();
        var result = _sut.GenerateRefreshToken(userId);
        result.Token.Should().NotBeNullOrEmpty();
        result.UserId.Should().Be(userId);
        result.ExpiresAt.Should().BeAfter(DateTime.UtcNow);
        result.FamilyId.Should().NotBeEmpty();
    }
}
