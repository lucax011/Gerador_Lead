using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;
using MotorAudiencia.Application.Options;

namespace MotorAudiencia.Infrastructure.Security;

public sealed class HmacValidator
{
    private const int MaxAgeSeconds = 30;
    private readonly string _secret;

    public HmacValidator(IOptions<SecurityOptions> options)
        => _secret = options.Value.ServiceSecret;

    public bool IsValid(string timestamp, string body, string signature)
    {
        if (!long.TryParse(timestamp, out var ts)) return false;
        var age = Math.Abs(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - ts);
        if (age > MaxAgeSeconds * 1000) return false;
        var expected = ComputeHmac(timestamp + body);
        return CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(expected),
            Encoding.UTF8.GetBytes(signature));
    }

    private string ComputeHmac(string data)
    {
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(_secret));
        return Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(data))).ToLower();
    }
}
