using System.Text.Json;
using TempHelper = MotorAudiencia.Domain.ValueObjects.Temperature;

namespace MotorAudiencia.Domain.Entities;

public sealed class Score
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    public Guid LeadId { get; private set; }
    public double Value { get; private set; }
    public string Temperature { get; private set; } = string.Empty;
    public string BreakdownJson { get; private set; } = "{}";
    public string? AiReason { get; private set; }
    public DateTime? UpdatedAt { get; private set; }
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;

    private Score() { }

    public static Score Create(Guid leadId, double value, string temperature, Dictionary<string, double> breakdown)
    {
        return new Score
        {
            LeadId = leadId,
            Value = value,
            Temperature = temperature,
            BreakdownJson = JsonSerializer.Serialize(breakdown),
        };
    }

    public void Refine(double adjustment, string reason)
    {
        Value = Math.Clamp(Math.Round(Value + adjustment, 2), 0, 100);
        Temperature = TempHelper.From(Value);
        AiReason = reason;
        UpdatedAt = DateTime.UtcNow;
    }
}
