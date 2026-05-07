namespace MotorAudiencia.Domain.Events;

public sealed record LeadOrchestratedMessage(
    Guid LeadId,
    Guid? CampaignId,
    string Approach,
    string Tone,
    string BestTime,
    string OpeningMessage,
    double FinalScore,
    string CorrelationId
);
