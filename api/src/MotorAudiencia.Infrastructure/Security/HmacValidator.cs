using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;
using MotorAudiencia.Application.Options;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Infrastructure.Security;

public sealed class HmacValidator : IHmacValidator
{
    private const int MaxAgeSeconds = 30;
    private readonly string _secret;

    public HmacValidator(IOptions<SecurityOptions> options)
        => _secret = options.Value.ServiceSecret;

    public bool IsValid(string timestamp, string body, string signature)
    {
        if (!long.TryParse(timestamp, out var ts)) return false;
        var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var diff = now - ts;
        if (diff < 0 || diff > MaxAgeSeconds * 1000) return false;

        var expected = ComputeHmac(timestamp + body);  // returns 64-char hex
        if (signature.Length != 64) return false;
        try
        {
            var expectedBytes = Convert.FromHexString(expected);
            var actualBytes = Convert.FromHexString(signature);
            return CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
        }
        catch (FormatException) { return false; }
    }

    private string ComputeHmac(string data)
    {
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(_secret));
        return Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(data))).ToLower();
    }
}
