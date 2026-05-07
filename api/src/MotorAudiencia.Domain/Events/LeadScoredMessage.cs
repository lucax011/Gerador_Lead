namespace MotorAudiencia.Domain.Events;

public sealed record LeadScoredMessage(
    Guid LeadId,
    Guid? CampaignId,
    double Score,
    string Temperature,
    string CorrelationId);
