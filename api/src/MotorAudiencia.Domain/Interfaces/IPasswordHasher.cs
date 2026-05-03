// Domain/Interfaces/IPasswordHasher.cs
namespace MotorAudiencia.Domain.Interfaces;

public interface IPasswordHasher
{
    string Hash(string password);
    bool Verify(string password, string storedHash);
}
