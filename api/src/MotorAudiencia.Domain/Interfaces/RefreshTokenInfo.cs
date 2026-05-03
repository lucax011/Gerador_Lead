namespace MotorAudiencia.Domain.Interfaces;

public sealed record RefreshTokenInfo(string Token, Guid FamilyId, Guid UserId, DateTime ExpiresAt, bool IsRevoked)
{
    public bool IsExpired => DateTime.UtcNow > ExpiresAt;
    public bool IsActive => !IsRevoked && !IsExpired;
}
