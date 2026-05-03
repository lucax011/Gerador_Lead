using FluentAssertions;
using Microsoft.Extensions.Options;
using MotorAudiencia.Application.Options;
using MotorAudiencia.Infrastructure.Security;

namespace MotorAudiencia.Tests.Security;

public class Argon2idPasswordHasherTests
{
    private readonly Argon2idPasswordHasher _sut;

    public Argon2idPasswordHasherTests()
    {
        var options = Options.Create(new SecurityOptions
        {
            AuthPepper = "test-pepper-32-chars-minimum-ok!",
            ServiceSecret = "test-secret-32-chars-minimum-ok!",
        });
        _sut = new Argon2idPasswordHasher(options);
    }

    [Fact]
    public void Hash_SamePassword_ProducesDifferentHashes()
    {
        _sut.Hash("senha123").Should().NotBe(_sut.Hash("senha123"));
    }

    [Fact]
    public void Verify_CorrectPassword_ReturnsTrue()
    {
        _sut.Verify("minha-senha", _sut.Hash("minha-senha")).Should().BeTrue();
    }

    [Fact]
    public void Verify_WrongPassword_ReturnsFalse()
    {
        _sut.Verify("senha-errada", _sut.Hash("minha-senha")).Should().BeFalse();
    }

    [Fact]
    public void Verify_TamperedHash_ReturnsFalse()
    {
        var hash = _sut.Hash("senha");
        _sut.Verify("senha", hash[..^4] + "XXXX").Should().BeFalse();
    }
}
