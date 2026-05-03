using System.Security.Cryptography;
using System.Text;
using Konscious.Security.Cryptography;
using Microsoft.Extensions.Options;
using MotorAudiencia.Application.Options;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Infrastructure.Security;

public sealed class Argon2idPasswordHasher : IPasswordHasher
{
    private const int MemorySize = 65536;
    private const int Iterations = 3;
    private const int DegreeOfParallelism = 1;
    private const int HashLength = 32;
    private const int SaltLength = 16;

    private readonly string _pepper;

    public Argon2idPasswordHasher(IOptions<SecurityOptions> options)
        => _pepper = options.Value.AuthPepper;

    public string Hash(string password)
    {
        var salt = RandomNumberGenerator.GetBytes(SaltLength);
        var hash = ComputeHash(password, salt);
        return $"{Convert.ToBase64String(salt)}:{Convert.ToBase64String(hash)}";
    }

    public bool Verify(string password, string storedHash)
    {
        var parts = storedHash.Split(':');
        if (parts.Length != 2) return false;
        try
        {
            var salt = Convert.FromBase64String(parts[0]);
            var expected = Convert.FromBase64String(parts[1]);
            var actual = ComputeHash(password, salt);
            return CryptographicOperations.FixedTimeEquals(actual, expected);
        }
        catch { return false; }
    }

    private byte[] ComputeHash(string password, byte[] salt)
    {
        var pepperedBytes = Encoding.UTF8.GetBytes(password + _pepper);
        using var argon2 = new Argon2id(pepperedBytes)
        {
            Salt = salt,
            MemorySize = MemorySize,
            Iterations = Iterations,
            DegreeOfParallelism = DegreeOfParallelism,
        };
        return argon2.GetBytes(HashLength);
    }
}
