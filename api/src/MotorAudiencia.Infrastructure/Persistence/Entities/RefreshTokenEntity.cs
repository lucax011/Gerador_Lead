using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace MotorAudiencia.Infrastructure.Persistence.Entities;

[Table("refresh_tokens")]
public sealed class RefreshTokenEntity
{
    [Key] public Guid Id { get; init; } = Guid.NewGuid();
    public string Token { get; init; } = string.Empty;
    public Guid FamilyId { get; init; }
    public Guid UserId { get; init; }
    public DateTime ExpiresAt { get; init; }
    public DateTime CreatedAt { get; init; } = DateTime.UtcNow;
    public bool IsRevoked { get; set; }

    public bool IsExpired => DateTime.UtcNow > ExpiresAt;
    public bool IsActive => !IsRevoked && !IsExpired;
}
