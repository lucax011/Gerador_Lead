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

    [Fact]
    public void ValidateAccessToken_WrongSigningKey_ReturnsNull()
    {
        var user = User.Create("admin", "hash");
        var wrongKeyService = new JwtService(Options.Create(new JwtOptions
        {
            Secret = "wrong-secret-must-be-at-least-64-chars-long-for-hmac-sha256-!!",
            Issuer = _opts.Issuer,
            Audience = _opts.Audience,
        }));
        var token = wrongKeyService.GenerateAccessToken(user);
        _sut.ValidateAccessToken(token).Should().BeNull();
    }

    [Fact]
    public void ValidateAccessToken_WrongIssuer_ReturnsNull()
    {
        var user = User.Create("admin", "hash");
        var wrongIssuerService = new JwtService(Options.Create(new JwtOptions
        {
            Secret = _opts.Secret,
            Issuer = "wrong-issuer",
            Audience = _opts.Audience,
        }));
        var token = wrongIssuerService.GenerateAccessToken(user);
        _sut.ValidateAccessToken(token).Should().BeNull();
    }

    [Fact]
    public void ValidateAccessToken_ExpiredToken_ReturnsNull()
    {
        var expiredService = new JwtService(Options.Create(new JwtOptions
        {
            Secret = _opts.Secret,
            Issuer = _opts.Issuer,
            Audience = _opts.Audience,
            AccessTokenMinutes = -1,  // already expired
        }));
        var user = User.Create("admin", "hash");
        var token = expiredService.GenerateAccessToken(user);
        _sut.ValidateAccessToken(token).Should().BeNull();
    }
}
