namespace MotorAudiencia.Domain.Interfaces;

public sealed record RefreshTokenResult(string Token, Guid FamilyId, Guid UserId, DateTime ExpiresAt);
