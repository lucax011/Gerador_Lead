namespace MotorAudiencia.Application.DTOs;

public sealed record LoginResponse(
    string AccessToken,
    DateTime ExpiresAt,
    string RefreshToken,
    DateTime RefreshExpiresAt);
