namespace MotorAudiencia.Domain.Events;

public sealed record LeadValidatedMessage(
    Guid LeadId,
    Guid? CampaignId,
    string CorrelationId);
