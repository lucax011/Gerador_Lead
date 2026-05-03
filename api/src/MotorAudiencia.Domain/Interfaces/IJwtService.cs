// Domain/Interfaces/IJwtService.cs
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface IJwtService
{
    string GenerateAccessToken(User user);
    RefreshTokenResult GenerateRefreshToken(Guid userId);
    Guid? ValidateAccessToken(string token);
}
