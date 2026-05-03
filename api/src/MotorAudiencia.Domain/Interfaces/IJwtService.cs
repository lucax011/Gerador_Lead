// Domain/Interfaces/IJwtService.cs
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Domain.Interfaces;

public interface IJwtService
{
    string GenerateAccessToken(User user);
    string GenerateRefreshToken(out Guid familyId, out DateTime expiresAt);
    Guid? ValidateAccessToken(string token);
}
