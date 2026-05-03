using System.ComponentModel.DataAnnotations;

namespace MotorAudiencia.Application.Options;

public sealed class JwtOptions
{
    public const string Section = "Jwt";

    [Required, MinLength(64)] public string Secret { get; set; } = string.Empty;
    [Required] public string Issuer { get; set; } = string.Empty;
    [Required] public string Audience { get; set; } = string.Empty;
    public int AccessTokenMinutes { get; set; } = 15;
    public int RefreshTokenDays { get; set; } = 7;
}
