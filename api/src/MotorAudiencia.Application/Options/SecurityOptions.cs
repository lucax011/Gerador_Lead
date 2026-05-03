using System.ComponentModel.DataAnnotations;

namespace MotorAudiencia.Application.Options;

public sealed class SecurityOptions
{
    public const string Section = "Security";

    [Required, MinLength(32)] public string AuthPepper { get; set; } = string.Empty;
    [Required, MinLength(32)] public string ServiceSecret { get; set; } = string.Empty;
}
