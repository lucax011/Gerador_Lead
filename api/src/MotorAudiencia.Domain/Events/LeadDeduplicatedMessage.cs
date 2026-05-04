namespace MotorAudiencia.Domain.Events;

public sealed record LeadDeduplicatedMessage(
    Guid LeadId,
    Guid? CampaignId,
    string CorrelationId);
