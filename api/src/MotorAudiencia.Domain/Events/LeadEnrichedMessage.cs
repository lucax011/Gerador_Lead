namespace MotorAudiencia.Domain.Events;

public sealed record LeadEnrichedMessage(
    Guid LeadId,
    Guid? CampaignId,
    string CorrelationId);
