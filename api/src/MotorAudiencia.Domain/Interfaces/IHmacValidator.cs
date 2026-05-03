namespace MotorAudiencia.Domain.Interfaces;

public interface IHmacValidator
{
    bool IsValid(string timestamp, string body, string signature);
}
